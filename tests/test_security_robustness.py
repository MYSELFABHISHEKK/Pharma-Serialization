import pytest
import time
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.core.database import Base, get_db
from app.models.db_models import AuditLog, User
from app.services.auth_service import AuthService
from app.core.security import validate_password_complexity, global_rate_limiter

# Setup in-memory test database for isolation
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
test_engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_test_db():
    Base.metadata.create_all(bind=test_engine)
    db = TestingSessionLocal()
    AuthService.seed_default_users(db)
    db.close()
    # Reset in-memory rate limiter between tests
    global_rate_limiter.reset()
    yield
    Base.metadata.drop_all(bind=test_engine)

# ====================================================================
# 1. OWASP Security Headers & Request Correlation Tracing
# ====================================================================

def test_owasp_security_headers_present():
    """Verify production-grade OWASP security headers on all responses."""
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    
    headers = resp.headers
    assert headers.get("X-Frame-Options") == "DENY"
    assert headers.get("X-Content-Type-Options") == "nosniff"
    assert "default-src 'self'" in headers.get("Content-Security-Policy", "")
    assert headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert "camera=()" in headers.get("Permissions-Policy", "")
    assert headers.get("X-XSS-Protection") == "1; mode=block"

def test_request_id_correlation_tracing():
    """Verify X-Request-ID propagation and auto-generation."""
    # 1. Generated if not supplied
    resp1 = client.get("/api/v1/health")
    assert resp1.status_code == 200
    req_id1 = resp1.headers.get("X-Request-ID")
    assert req_id1 is not None
    assert len(req_id1) > 0

    # 2. Preserved if supplied by client / gateway
    custom_id = "trace-corp-plant-hyd-98765"
    resp2 = client.get("/api/v1/health", headers={"X-Request-ID": custom_id})
    assert resp2.status_code == 200
    assert resp2.headers.get("X-Request-ID") == custom_id
    assert resp2.json()["request_id"] == custom_id

# ====================================================================
# 2. 21 CFR Part 11 / GAMP 5 Password Complexity
# ====================================================================

def test_password_complexity_validation():
    """Verify password complexity requirements enforce regulatory standards."""
    # Too short (< 8 chars)
    valid, msg = validate_password_complexity("Ab1!")
    assert not valid
    assert "at least 8 characters" in msg

    # Missing uppercase
    valid, msg = validate_password_complexity("alllowercase123!")
    assert not valid
    assert "uppercase" in msg

    # Missing lowercase
    valid, msg = validate_password_complexity("ALLUPPERCASE123!")
    assert not valid
    assert "lowercase" in msg

    # Missing numeric digit
    valid, msg = validate_password_complexity("NoDigitsAllowed!@#")
    assert not valid
    assert "digit" in msg

    # Missing special character
    valid, msg = validate_password_complexity("NoSpecialChars123")
    assert not valid
    assert "special character" in msg

    # Common blacklisted password
    valid, msg = validate_password_complexity("Password123!")
    assert not valid
    assert "easily guessable" in msg

    # Fully compliant password
    valid, msg = validate_password_complexity("SecurePlant#2026")
    assert valid
    assert not msg

def test_password_complexity_enforced_on_registration():
    """Ensure API rejects weak passwords during user provisioning."""
    # Login as admin
    login_resp = client.post("/api/v1/auth/login", json={"username": "admin", "password": "Admin@1234"})
    assert login_resp.status_code == 200
    admin_token = login_resp.json()["access_token"]

    # Provision user with password missing uppercase
    weak_payload = {
        "username": "weak_user",
        "email": "weak@pharma.local",
        "full_name": "Weak User",
        "password": "validpattern123!",
        "role": "Serialization Operator"
    }
    resp = client.post(
        "/api/v1/auth/users",
        json=weak_payload,
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert resp.status_code == 400
    assert "uppercase" in resp.json()["detail"].lower()

# ====================================================================
# 3. Rate Limiting on Login Endpoint
# ====================================================================

def test_login_rate_limiting():
    """Verify sliding-window rate limiting on login prevents brute force."""
    # Maximum allowed attempts is 25 per minute
    for _ in range(25):
        resp = client.post("/api/v1/auth/login", json={"username": "fake_user", "password": "FakePassword@123"})
        # Should be 401 unauthorized
        assert resp.status_code in [400, 401]

    # 26th request must be rejected with 429 Too Many Requests
    resp_blocked = client.post("/api/v1/auth/login", json={"username": "fake_user", "password": "FakePassword@123"})
    assert resp_blocked.status_code == 429
    assert "Retry-After" in resp_blocked.headers
    assert "Too many authentication attempts" in resp_blocked.json()["detail"]

# ====================================================================
# 4. Audit Log Immutability Guard (21 CFR Part 11 Non-Repudiation)
# ====================================================================

def test_audit_log_immutability():
    """Verify audit log records cannot be updated or deleted by any process."""
    from datetime import datetime, timezone
    db = TestingSessionLocal()
    try:
        # Create an audit log record with serialized JSON and timestamp
        log_entry = AuditLog(
            event_type="SYSTEM_TEST",
            table_name="products",
            record_id="PROD-999",
            previous_value=None,
            updated_value='{"name": "Test Capsule"}',
            performed_by="qa_tester",
            client_ip="192.168.1.100",
            request_id="test-req-001",
            timestamp=datetime.now(timezone.utc).isoformat()
        )
        db.add(log_entry)
        db.commit()
        db.refresh(log_entry)
        entry_id = log_entry.id

        # Attempt to modify the audit log record (must fail)
        log_entry.performed_by = "malicious_actor"
        with pytest.raises(ValueError, match="Audit trail records are permanently immutable"):
            db.commit()

        db.rollback()

        # Attempt to delete the audit log record (must fail)
        record_to_del = db.query(AuditLog).filter(AuditLog.id == entry_id).first()
        db.delete(record_to_del)
        with pytest.raises(ValueError, match="Audit trail records are permanently immutable"):
            db.commit()

    finally:
        db.close()

# ====================================================================
# 5. Deep Health Check & Pool Diagnostics
# ====================================================================

def test_enhanced_health_check():
    """Verify deep health check returns DB latency, connection status, and pool details."""
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    
    assert data["status"] == "healthy"
    assert data["database"] == "connected"
    assert "latency_ms" in data
    assert isinstance(data["latency_ms"], (int, float))
    assert "pool" in data
    assert "request_id" in data

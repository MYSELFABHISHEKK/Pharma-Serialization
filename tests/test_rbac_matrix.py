import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.models.db_models import User, Role, AuditLog
from app.services.auth_service import AuthService
from app.services.rbac_service import RBACService

client = TestClient(app)

def test_unauthenticated_request_rejected(db_session):
    """Endpoints protected by RBAC should return 401 when no token is provided."""
    # Ensure client has no authorization header
    unauth_client = TestClient(app)
    res = unauth_client.get("/api/v1/products")
    assert res.status_code == 401
    assert "Authentication required" in res.json().get("detail", "")

def test_invalid_session_token_rejected(db_session):
    """Invalid bearer token should return 401 Unauthorized."""
    res = client.get("/api/v1/products", headers={"Authorization": "Bearer invalid-token-xyz"})
    assert res.status_code == 401
    assert "expired or been revoked" in res.json().get("detail", "")

def test_account_lockout_after_failed_attempts(db_session):
    """5 failed login attempts should lock the account."""
    # Attempt 5 incorrect logins for operator
    for _ in range(5):
        res = client.post("/api/v1/auth/login", json={
            "username": "operator",
            "password": "WrongPassword!999"
        })
        assert res.status_code == 401

    # 6th attempt with CORRECT password should now be locked
    res = client.post("/api/v1/auth/login", json={
        "username": "operator",
        "password": "Operator@1234"
    })
    assert res.status_code == 401
    assert "locked" in res.json().get("detail", "").lower()

def test_operator_permission_boundaries(db_session):
    """Operator role should be restricted from admin actions but allowed operational workflows."""
    # Authenticate as operator
    # Reset lockout if any
    op_user = db_session.query(User).filter(User.username == "operator").first()
    op_user.failed_login_attempts = 0
    op_user.locked_until = None
    db_session.commit()

    res = client.post("/api/v1/auth/login", json={
        "username": "operator",
        "password": "Operator@1234"
    })
    assert res.status_code == 200
    token = res.json()["token"]
    op_headers = {"Authorization": f"Bearer {token}"}

    # 1. Operator CAN view batches
    res = client.get("/api/v1/serialization/batches", headers=op_headers)
    assert res.status_code == 200

    # 2. Operator CANNOT create products (needs products:create)
    res = client.post("/api/v1/products", json={
        "product_id": "OP-PROD-DENIED",
        "name": "Operator Product",
        "gtin": "11112222333344",
        "status": "ACTIVE",
        "profile": {"length": 15, "allow_duplicate_characters": False}
    }, headers=op_headers)
    assert res.status_code == 403
    assert "Access Denied" in res.json().get("detail", "")

    # 3. Operator CANNOT access user management
    res = client.get("/api/v1/auth/users", headers=op_headers)
    assert res.status_code == 403

    # 4. Operator CANNOT access roles & privileges
    res = client.get("/api/v1/auth/roles", headers=op_headers)
    assert res.status_code == 403

def test_read_only_auditor_permissions(db_session):
    """Auditor role can inspect data but cannot create, modify, or execute batches."""
    auditor_role = db_session.query(Role).filter(Role.role_name == "Read-Only Auditor").first()
    auditor_user, token, _ = AuthService.register_user(
        db=db_session,
        req=type('Obj', (object,), {
            "username": "auditor_jane",
            "email": "jane.auditor@pharma.local",
            "full_name": "Jane Auditor",
            "password": "Auditor@1234",
            "role": "Read-Only Auditor",
            "role_id": auditor_role.id,
            "plant": "TESTPLANT"
        })(),
        role_id=auditor_role.id
    )
    aud_headers = {"Authorization": f"Bearer {token}"}

    # Auditor CAN view audit logs
    res = client.get("/api/v1/audit-logs", headers=aud_headers)
    assert res.status_code == 200

    # Auditor CAN view batches
    res = client.get("/api/v1/serialization/batches", headers=aud_headers)
    assert res.status_code == 200

    # Auditor CANNOT generate serials
    res = client.post("/api/v1/serialization/generate", json={
        "product_id": "TEST-PROD",
        "quantity": 5,
        "batch_lot": "LOT-AUD-1",
        "expiry_date": "301231"
    }, headers=aud_headers)
    assert res.status_code == 403

def test_admin_full_access_and_role_management(db_session):
    """Admin has full privileges and can create/update custom roles."""
    admin = db_session.query(User).filter(User.username == "admin").first()
    admin_token, _ = AuthService.create_session(db_session, admin)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # List roles
    res = client.get("/api/v1/auth/roles", headers=admin_headers)
    assert res.status_code == 200
    roles = res.json()
    assert len(roles) >= 4

    # Create custom role
    res = client.post("/api/v1/auth/roles", json={
        "role_name": "Warehouse Dispatcher",
        "description": "Packaging aggregation and verification only",
        "permissions": {
            "dashboard": ["view"],
            "verification": ["view", "verify"]
        }
    }, headers=admin_headers)
    assert res.status_code == 200
    created_role = res.json()
    assert created_role["role_name"] == "Warehouse Dispatcher"
    role_id = created_role["id"]

    # Delete custom role
    del_res = client.delete(f"/api/v1/auth/roles/{role_id}", headers=admin_headers)
    assert del_res.status_code == 200

    # Verify 21 CFR Part 11 audit records were generated
    events = [e[0] for e in db_session.query(AuditLog.event_type).all()]
    assert "ROLE_CREATED" in events
    assert "ROLE_DELETED" in events

def test_user_deactivation_revokes_sessions(db_session):
    """Deactivating a user must immediately revoke their active sessions."""
    admin = db_session.query(User).filter(User.username == "admin").first()
    admin_token, _ = AuthService.create_session(db_session, admin)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # Create temporary operator
    op_role = db_session.query(Role).filter(Role.role_name == "Serialization Operator").first()
    temp_user, op_token, _ = AuthService.register_user(
        db=db_session,
        req=type('Obj', (object,), {
            "username": "temp_op",
            "email": "temp_op@pharma.local",
            "full_name": "Temporary Operator",
            "password": "TempOp@1234",
            "role": "Serialization Operator",
            "role_id": op_role.id,
            "plant": "TESTPLANT"
        })(),
        role_id=op_role.id
    )
    temp_headers = {"Authorization": f"Bearer {op_token}"}

    # Verify temp_op can call batches
    res = client.get("/api/v1/serialization/batches", headers=temp_headers)
    assert res.status_code == 200

    # Admin deactivates temp_op
    deact_res = client.patch(f"/api/v1/auth/users/{temp_user.id}/status", json={"is_active": False}, headers=admin_headers)
    assert deact_res.status_code == 200
    assert deact_res.json()["is_active"] is False

    # Immediate check: temp_op's existing session token should now be rejected
    after_res = client.get("/api/v1/serialization/batches", headers=temp_headers)
    assert after_res.status_code == 401

def test_user_password_change_and_reset(db_session):
    """User can change password and admin can reset password with force flag."""
    admin = db_session.query(User).filter(User.username == "admin").first()
    admin_token, _ = AuthService.create_session(db_session, admin)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # 1. Admin resets operator password
    op_user = db_session.query(User).filter(User.username == "operator").first()
    reset_res = client.post(f"/api/v1/auth/users/{op_user.id}/reset-password", json={
        "new_password": "NewTempPassword@123",
        "require_password_change": True
    }, headers=admin_headers)
    assert reset_res.status_code == 200

    # 2. Operator logs in with new temporary password
    login_res = client.post("/api/v1/auth/login", json={
        "username": "operator",
        "password": "NewTempPassword@123"
    })
    assert login_res.status_code == 200
    auth_data = login_res.json()
    assert auth_data["require_password_change"] is True
    op_token = auth_data["token"]

    # 3. Operator changes password
    change_res = client.post("/api/v1/auth/change-password", json={
        "old_password": "NewTempPassword@123",
        "new_password": "PermanentPassword@987"
    }, headers={"Authorization": f"Bearer {op_token}"})
    assert change_res.status_code == 200

    # 4. Verify new permanent password works
    re_login = client.post("/api/v1/auth/login", json={
        "username": "operator",
        "password": "PermanentPassword@987"
    })
    assert re_login.status_code == 200
    assert re_login.json()["require_password_change"] is False

def test_user_level_permission_override(db_session):
    """User override should take precedence over role permissions."""
    admin = db_session.query(User).filter(User.username == "admin").first()
    admin_token, _ = AuthService.create_session(db_session, admin)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    op_user = db_session.query(User).filter(User.username == "operator").first()
    op_token, _ = AuthService.create_session(db_session, op_user)
    op_headers = {"Authorization": f"Bearer {op_token}"}

    # Operator initially cannot create products
    res = client.post("/api/v1/products", json={
        "product_id": "OVERRIDE-PROD-1",
        "name": "Override Product",
        "gtin": "88887777666655",
        "status": "ACTIVE",
        "profile": {"length": 15, "allow_duplicate_characters": False}
    }, headers=op_headers)
    assert res.status_code == 403

    # Admin grants explicit override for products:create to operator
    override_res = client.patch(f"/api/v1/auth/users/{op_user.id}/permissions", json={
        "module_key": "products",
        "action_key": "create",
        "is_allowed": True
    }, headers=admin_headers)
    assert override_res.status_code == 200

    # Operator now CAN create products!
    res = client.post("/api/v1/products", json={
        "product_id": "OVERRIDE-PROD-1",
        "name": "Override Product",
        "gtin": "88887777666655",
        "status": "ACTIVE",
        "profile": {"length": 15, "allow_duplicate_characters": False}
    }, headers=op_headers)
    assert res.status_code == 200

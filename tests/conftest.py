import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.database import Base, get_db
from app.models.db_models import User
from app.services.auth_service import AuthService
from app.api.deps import get_current_user
from app.main import app

@pytest.fixture(name="db_session", autouse=True)
def db_session_fixture(request):
    """
    Creates an in-memory SQLite database instance for isolated test runs.
    Overrides FastAPI's database session generator 'get_db' and seeds default RBAC data.
    """
    from sqlalchemy.pool import StaticPool
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    # Seed default RBAC roles and users
    AuthService.seed_default_users(session)
    admin = session.query(User).filter(User.username == "admin").first()

    # Override get_db dependency injection in FastAPI routers
    def override_get_db():
        try:
            yield session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    # For legacy serialization tests that don't test auth/RBAC, provide default admin user
    nodeid = getattr(request.node, "nodeid", "")
    is_auth_test = "test_rbac_matrix" in nodeid or "test_auth" in nodeid
    if not is_auth_test:
        app.dependency_overrides[get_current_user] = lambda: admin
    else:
        app.dependency_overrides.pop(get_current_user, None)
    
    yield session
    
    session.close()
    app.dependency_overrides.clear()

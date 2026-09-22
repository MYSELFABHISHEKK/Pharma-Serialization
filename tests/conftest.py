import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.database import Base, get_db
from app.models.db_models import Product, Batch, Serial, SGTINCode, ProductSequence, Idempotency
from app.main import app

@pytest.fixture(name="db_session", autouse=True)
def db_session_fixture():
    """
    Creates an in-memory SQLite database instance for isolated test runs.
    Overrides FastAPI's database session generator 'get_db'.
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

    # Override get_db dependency injection in FastAPI routers
    def override_get_db():
        try:
            yield session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    
    yield session
    
    session.close()
    app.dependency_overrides.clear()

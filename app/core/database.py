import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings

logger = logging.getLogger("bt_sn_portal")

# SQLite needs separate thread settings, while PostgreSQL does not
connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}

try:
    engine = create_engine(
        settings.DATABASE_URL, 
        connect_args=connect_args,
        pool_pre_ping=True  # Automatically checks and recycles dead connections
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base = declarative_base()
    logger.info("SQLAlchemy Database engine initialized.")
except Exception as e:
    logger.error(f"Failed to initialize SQLAlchemy database engine: {e}")
    raise e

def get_db():
    """Dependency for providing database sessions to endpoints."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

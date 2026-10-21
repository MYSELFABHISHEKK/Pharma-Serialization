
import logging

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.core.config import settings

logger = logging.getLogger("bt_sn_portal")

# Read the database URL from your environment configuration
DATABASE_URL = settings.DATABASE_URL

# Render / Cloud hosts often supply postgres:// instead of postgresql://
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Configure SQLite separately; PostgreSQL does not need this setting
connect_args = (
    {"check_same_thread": False}
    if DATABASE_URL.startswith("sqlite")
    else {}
)

try:
    # Initialize the SQLAlchemy database engine
    engine = create_engine(
        DATABASE_URL,
        connect_args=connect_args,
        pool_pre_ping=True,
    )

    # Create a factory for database sessions
    SessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
    )

    # Base class for SQLAlchemy models
    Base = declarative_base()

    logger.info("SQLAlchemy database engine initialized.")

except Exception:
    logger.exception("Failed to initialize SQLAlchemy database engine.")
    raise


def get_db():
    """Provide a database session to FastAPI endpoints."""
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()

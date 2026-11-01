
import logging
import time
from typing import Callable, Any, Dict
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.exc import OperationalError, DBAPIError

from app.core.config import settings

logger = logging.getLogger("bt_sn_portal")

# Read the database URL from your environment configuration
DATABASE_URL = settings.DATABASE_URL

# Render / Cloud hosts often supply postgres:// instead of postgresql://
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

is_sqlite = DATABASE_URL.startswith("sqlite")

# Configure connection parameters based on engine backend
connect_args = {"check_same_thread": False} if is_sqlite else {}

engine_kwargs: Dict[str, Any] = {
    "connect_args": connect_args,
    "pool_pre_ping": True,  # Actively tests connection liveness before checking out
}

if not is_sqlite:
    # Enterprise PostgreSQL Connection Pool settings for cloud & plant intranet reliability
    engine_kwargs.update({
        "pool_size": 10,           # Baseline pooled connections
        "max_overflow": 20,        # Burst headroom for high-volume batch runs
        "pool_recycle": 300,       # Recycle connection after 5 mins to prevent idle TCP drops
        "pool_timeout": 30,        # Wait up to 30s for an available pool slot
    })

try:
    # Initialize the SQLAlchemy database engine
    engine = create_engine(DATABASE_URL, **engine_kwargs)

    # Create a factory for database sessions
    SessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
    )

    # Base class for SQLAlchemy models
    Base = declarative_base()

    logger.info("SQLAlchemy database engine initialized with enterprise pooling.")

except Exception:
    logger.exception("Failed to initialize SQLAlchemy database engine.")
    raise


def get_db():
    """Provide a database session to FastAPI endpoints with auto-cleanup."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def with_db_retry(operation: Callable[..., Any], max_retries: int = 3, initial_delay: float = 0.2) -> Any:
    """
    Executes a database operation with exponential backoff retry logic.
    Handles transient network blips, TCP timeouts, and connection reset errors.
    """
    attempt = 0
    delay = initial_delay
    last_exception = None

    while attempt < max_retries:
        try:
            return operation()
        except (OperationalError, DBAPIError) as e:
            attempt += 1
            last_exception = e
            if attempt >= max_retries:
                logger.error(f"Database operation failed permanently after {max_retries} attempts: {e}")
                raise
            logger.warning(f"Database transient error encountered (attempt {attempt}/{max_retries}). Retrying in {delay:.2f}s... Error: {e}")
            time.sleep(delay)
            delay *= 2  # Exponential backoff

    if last_exception:
        raise last_exception


def get_db_pool_status() -> Dict[str, Any]:
    """Returns real-time connection pool diagnostics for health monitoring."""
    if is_sqlite:
        return {"backend": "sqlite", "pool": "in_memory_or_file"}
    
    pool = engine.pool
    return {
        "backend": "postgresql",
        "pool_size": getattr(pool, "size", lambda: 10)(),
        "checked_in": getattr(pool, "checkedin", lambda: 0)(),
        "checked_out": getattr(pool, "checkedout", lambda: 0)(),
        "overflow": getattr(pool, "overflow", lambda: 0)(),
    }

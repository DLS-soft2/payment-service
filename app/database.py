"""
Database engine and session factory.

Creates the SQLAlchemy engine from the DATABASE_URL setting
and provides a dependency (get_db) that FastAPI endpoints
can use to get a database session per request.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.config import settings

# The engine manages the connection pool to PostgreSQL
engine = create_engine(settings.database_url)

# Each request gets its own session via this factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# All database models inherit from this base class
Base = declarative_base()


def get_db():
    """
    FastAPI dependency that provides a database session.

    Usage in an endpoint:
        @router.get("/payments")
        def list_payments(db: Session = Depends(get_db)):
            ...

    The session is automatically closed when the request finishes,
    even if an error occurs (thanks to the finally block).
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

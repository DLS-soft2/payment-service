"""
Test fixtures for Payment Service.

Uses SQLite in-memory instead of PostgreSQL so tests run instantly
without needing a database server. This is the same approach
used in the User Service.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app

# SQLite in-memory — created fresh for each test, thrown away after
SQLALCHEMY_TEST_URL = "sqlite:///./test.db"
test_engine = create_engine(
    SQLALCHEMY_TEST_URL, connect_args={"check_same_thread": False}
)
TestSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(name="db")
def fixture_db():
    """Create a fresh database for each test."""
    Base.metadata.create_all(bind=test_engine)
    db = TestSession()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(name="client")
def fixture_client(db):
    """HTTP test client with the test database injected."""
    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()

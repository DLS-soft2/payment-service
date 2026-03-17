"""
Test fixtures for Payment Service.

Uses SQLite in-memory instead of PostgreSQL and disables Kafka
so tests run instantly without needing any infrastructure.
"""

import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import database
from app.database import Base, get_db
from app.main import app

# SQLite in-memory — created fresh for each test
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
    """
    HTTP test client with the test database injected
    and Kafka disabled.

    We mock out the Kafka producer and consumer so that:
    - Tests don't need a running Kafka broker
    - Tests run fast (no network calls)
    - We can test the REST API in isolation
    """
    # Patch the database engine so lifespan uses SQLite
    original_engine = database.engine
    database.engine = test_engine

    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    # Mock Kafka producer and consumer so they don't actually connect
    with patch("app.main.start_producer", new_callable=AsyncMock), \
         patch("app.main.stop_producer", new_callable=AsyncMock), \
         patch("app.main.start_consumer", new_callable=AsyncMock):
        with TestClient(app) as client:
            yield client

    database.engine = original_engine
    app.dependency_overrides.clear()

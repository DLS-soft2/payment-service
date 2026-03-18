"""
Tests for Payment Service REST endpoints.

These test the read-only API. Payment creation will be tested
separately once Kafka integration is added.
"""

import uuid

from app.models import Payment


def test_root(client):
    """Service info endpoint returns name and version."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "payment-service"


def test_health(client):
    """Health check returns healthy status."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_list_payments_empty(client):
    """Listing payments on a fresh database returns an empty list."""
    response = client.get("/v1/payments/")
    assert response.status_code == 200
    assert response.json() == []


def test_get_payment_not_found(client):
    """Fetching a non-existent payment returns 404."""
    fake_id = uuid.uuid4()
    response = client.get(f"/v1/payments/{fake_id}")
    assert response.status_code == 404


def test_list_payments_with_data(client, db):
    """Listing payments returns inserted records."""
    # Insert a payment directly into the test database
    payment = Payment(
        order_id=uuid.uuid4(),
        amount=99.50,
        status="AUTHORIZED",
    )
    db.add(payment)
    db.commit()

    response = client.get("/v1/payments/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["amount"] == 99.50
    assert data[0]["status"] == "AUTHORIZED"


def test_get_payments_by_order(client, db):
    """Fetching payments by order_id returns matching records."""
    order_id = uuid.uuid4()

    # Insert two payments for the same order
    for status in ["FAILED", "AUTHORIZED"]:
        payment = Payment(order_id=order_id, amount=150.0, status=status)
        db.add(payment)
    db.commit()

    response = client.get(f"/v1/payments/order/{order_id}")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2

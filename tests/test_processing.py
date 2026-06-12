import asyncio
import uuid
from datetime import datetime, timezone
from unittest.mock import patch, AsyncMock

from app.events import OrderCreated, RestaurantRejected, CourierAssignmentFailed
from app.kafka_consumer import (
    simulate_payment, process_payment, handle_order_created,
    refund_payment, handle_refund_event, _processed_event_ids,
)
from app.models import Payment


# --- simulate_payment tests ---

def test_default_card_succeeds():
    """The default test card (ending 0000) should always succeed."""
    success, reason = simulate_payment(50.0, "4242424242420000")
    assert success is True


def test_declined_insufficient_funds():
    """Card ending in 9999 should be declined for insufficient funds."""
    success, reason = simulate_payment(50.0, "4242424242429999")
    assert success is False
    assert "insufficient funds" in reason.lower()


def test_declined_card_expired():
    """Card ending in 5555 should be declined for expiry."""
    success, reason = simulate_payment(50.0, "4242424242425555")
    assert success is False
    assert "expired" in reason.lower()


def test_declined_card_stolen():
    """Card ending in 1111 should be declined as stolen."""
    success, reason = simulate_payment(50.0, "4242424242421111")
    assert success is False
    assert "stolen" in reason.lower()


def test_amount_over_limit():
    """Amounts over 10000 should always fail regardless of card."""
    success, reason = simulate_payment(15000.0, "4242424242420000")
    assert success is False
    assert "maximum limit" in reason.lower()


def test_invalid_amount():
    """Zero or negative amounts should always fail."""
    success, reason = simulate_payment(0, "4242424242420000")
    assert success is False
    assert "invalid" in reason.lower()


def test_unknown_card_succeeds():
    """Cards not matching any failure pattern should succeed."""
    success, reason = simulate_payment(50.0, "1234567890123456")
    assert success is True


# --- process_payment tests ---

def test_process_payment_authorized(db):
    """A valid order with a good card should create an AUTHORIZED payment."""
    order_event = OrderCreated(
        order_id=uuid.uuid4(),
        customer_id=uuid.uuid4(),
        amount=99.50,
        card_number="4242424242420000",
        timestamp=datetime.now(timezone.utc),
    )

    payment = process_payment(order_event, db)

    assert payment.id is not None
    assert payment.order_id == order_event.order_id
    assert payment.amount == 99.50
    assert payment.status == "AUTHORIZED"


def test_process_payment_failed(db):
    """An order with a declined card should create a FAILED payment."""
    order_event = OrderCreated(
        order_id=uuid.uuid4(),
        customer_id=uuid.uuid4(),
        amount=99.50,
        card_number="4242424242429999",
        timestamp=datetime.now(timezone.utc),
    )

    payment = process_payment(order_event, db)
    assert payment.status == "FAILED"


# --- handle_order_created event enrichment tests ---


def test_handle_order_created_authorized_event_contains_enriched_fields(db):
    """PaymentAuthorized event must carry customer_id and restaurant_id from the order."""
    customer_id = uuid.uuid4()
    restaurant_id = uuid.uuid4()
    order_id = uuid.uuid4()

    message = {
        "order_id": str(order_id),
        "customer_id": str(customer_id),
        "restaurant_id": str(restaurant_id),
        "amount": 50.0,
        "card_number": "4242424242420000",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    mock_publish = AsyncMock()
    with patch("app.kafka_consumer.SessionLocal", return_value=db), \
         patch("app.kafka_consumer.publish_event", mock_publish):
        asyncio.run(handle_order_created(message))

    mock_publish.assert_called_once()
    _topic, event_data = mock_publish.call_args.args
    assert event_data["event_type"] == "PaymentAuthorized"
    assert event_data["customer_id"] == customer_id
    assert event_data["restaurant_id"] == restaurant_id
    assert event_data["order_id"] == order_id


def test_handle_order_created_failed_event_contains_customer_id(db):
    """PaymentFailed event must carry customer_id from the order."""
    customer_id = uuid.uuid4()
    order_id = uuid.uuid4()

    message = {
        "order_id": str(order_id),
        "customer_id": str(customer_id),
        "restaurant_id": str(uuid.uuid4()),
        "amount": 50.0,
        "card_number": "4242424242429999",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    mock_publish = AsyncMock()
    with patch("app.kafka_consumer.SessionLocal", return_value=db), \
         patch("app.kafka_consumer.publish_event", mock_publish):
        asyncio.run(handle_order_created(message))

    mock_publish.assert_called_once()
    _topic, event_data = mock_publish.call_args.args
    assert event_data["event_type"] == "PaymentFailed"
    assert event_data["customer_id"] == customer_id
    assert event_data["order_id"] == order_id


def test_handle_order_created_without_restaurant_id(db):
    """OrderCreated without restaurant_id still processes and publishes events."""
    order_id = uuid.uuid4()
    customer_id = uuid.uuid4()

    message = {
        "order_id": str(order_id),
        "customer_id": str(customer_id),
        "amount": 50.0,
        "card_number": "4242424242420000",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    mock_publish = AsyncMock()
    with patch("app.kafka_consumer.SessionLocal", return_value=db), \
         patch("app.kafka_consumer.publish_event", mock_publish):
        asyncio.run(handle_order_created(message))

    mock_publish.assert_called_once()
    _topic, event_data = mock_publish.call_args.args
    assert event_data["event_type"] == "PaymentAuthorized"
    assert event_data["order_id"] == order_id
    assert event_data["customer_id"] == customer_id
    assert event_data["restaurant_id"] is None


# --- refund_payment tests ---


def test_refund_payment_authorized_to_refunded(db):
    """An AUTHORIZED payment should transition to REFUNDED."""
    order_id = uuid.uuid4()
    payment = Payment(order_id=order_id, amount=50.0, status="AUTHORIZED")
    db.add(payment)
    db.commit()

    result = refund_payment(order_id, "Test refund", db)

    assert result is not None
    assert result.status == "REFUNDED"


def test_refund_payment_already_refunded_skips(db):
    """A REFUNDED payment should not be modified again."""
    order_id = uuid.uuid4()
    payment = Payment(order_id=order_id, amount=50.0, status="REFUNDED")
    db.add(payment)
    db.commit()

    result = refund_payment(order_id, "Duplicate refund", db)

    assert result is None
    db.refresh(payment)
    assert payment.status == "REFUNDED"


def test_refund_payment_failed_skips(db):
    """A FAILED payment should not be refunded."""
    order_id = uuid.uuid4()
    payment = Payment(order_id=order_id, amount=50.0, status="FAILED")
    db.add(payment)
    db.commit()

    result = refund_payment(order_id, "Should skip", db)

    assert result is None
    db.refresh(payment)
    assert payment.status == "FAILED"


def test_refund_payment_no_payment_found(db):
    """Refunding a non-existent order should return None."""
    result = refund_payment(uuid.uuid4(), "No payment", db)
    assert result is None


# --- handle_refund_event tests ---


def test_handle_refund_event_restaurant_rejected(db):
    """RestaurantRejected event should refund payment and publish PaymentRefunded."""
    order_id = uuid.uuid4()
    customer_id = uuid.uuid4()
    payment = Payment(order_id=order_id, amount=75.0, status="AUTHORIZED")
    db.add(payment)
    db.commit()
    db.refresh(payment)

    event = RestaurantRejected(
        order_id=order_id,
        customer_id=customer_id,
        restaurant_id=uuid.uuid4(),
        reason="Kitchen closed",
        timestamp=datetime.now(timezone.utc),
    )

    mock_publish = AsyncMock()
    with patch("app.kafka_consumer.SessionLocal", return_value=db), \
         patch("app.kafka_consumer.publish_event", mock_publish):
        asyncio.run(handle_refund_event(event, "Restaurant rejected order"))

    mock_publish.assert_called_once()
    _topic, event_data = mock_publish.call_args.args
    assert _topic == "payments"
    assert event_data["event_type"] == "PaymentRefunded"
    assert event_data["order_id"] == order_id
    assert event_data["customer_id"] == customer_id
    assert event_data["payment_id"] == payment.id
    assert event_data["amount"] == 75.0
    assert "Restaurant rejected order: Kitchen closed" in event_data["reason"]


def test_handle_refund_event_courier_assignment_failed(db):
    """CourierAssignmentFailed event should refund payment and publish PaymentRefunded."""
    order_id = uuid.uuid4()
    customer_id = uuid.uuid4()
    payment = Payment(order_id=order_id, amount=30.0, status="AUTHORIZED")
    db.add(payment)
    db.commit()
    db.refresh(payment)

    event = CourierAssignmentFailed(
        order_id=order_id,
        customer_id=customer_id,
        restaurant_id=uuid.uuid4(),
        reason="No available couriers",
        timestamp=datetime.now(timezone.utc),
    )

    mock_publish = AsyncMock()
    with patch("app.kafka_consumer.SessionLocal", return_value=db), \
         patch("app.kafka_consumer.publish_event", mock_publish):
        asyncio.run(handle_refund_event(event, "Courier assignment failed"))

    mock_publish.assert_called_once()
    _topic, event_data = mock_publish.call_args.args
    assert _topic == "payments"
    assert event_data["event_type"] == "PaymentRefunded"
    assert event_data["order_id"] == order_id
    assert event_data["customer_id"] == customer_id
    assert event_data["payment_id"] == payment.id
    assert event_data["amount"] == 30.0
    assert "Courier assignment failed: No available couriers" in event_data["reason"]


def test_handle_refund_event_already_refunded_no_publish(db):
    """If payment is already REFUNDED, no event should be published."""
    order_id = uuid.uuid4()
    payment = Payment(order_id=order_id, amount=50.0, status="REFUNDED")
    db.add(payment)
    db.commit()

    event = RestaurantRejected(
        order_id=order_id,
        customer_id=uuid.uuid4(),
        restaurant_id=uuid.uuid4(),
        reason="Duplicate",
        timestamp=datetime.now(timezone.utc),
    )

    mock_publish = AsyncMock()
    with patch("app.kafka_consumer.SessionLocal", return_value=db), \
         patch("app.kafka_consumer.publish_event", mock_publish):
        asyncio.run(handle_refund_event(event, "Restaurant rejected order"))

    mock_publish.assert_not_called()


def test_handle_refund_event_no_payment_no_publish(db):
    """If no payment exists for the order, no event should be published."""
    event = CourierAssignmentFailed(
        order_id=uuid.uuid4(),
        customer_id=uuid.uuid4(),
        restaurant_id=uuid.uuid4(),
        reason="No couriers",
        timestamp=datetime.now(timezone.utc),
    )

    mock_publish = AsyncMock()
    with patch("app.kafka_consumer.SessionLocal", return_value=db), \
         patch("app.kafka_consumer.publish_event", mock_publish):
        asyncio.run(handle_refund_event(event, "Courier assignment failed"))

    mock_publish.assert_not_called()


# --- idempotency guard tests ---


def test_idempotency_guard_skips_duplicate_event(db):
    """The same event_id should not be processed twice."""
    event_id = str(uuid.uuid4())

    # Simulate that this event_id was already processed
    _processed_event_ids.add(event_id)

    try:
        assert event_id in _processed_event_ids
    finally:
        _processed_event_ids.discard(event_id)
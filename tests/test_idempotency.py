import uuid
from datetime import datetime, timezone
from unittest.mock import patch, AsyncMock

import pytest

from app.kafka_consumer import (
    is_event_processed, mark_event_processed, _route_event,
)
from app.models import Payment, ProcessedEvent


def _make_order_message(event_id: str, order_id: str | None = None) -> dict:
    """Build a minimal OrderCreated message dict for testing."""
    return {
        "event_id": event_id,
        "event_type": "OrderCreated",
        "order_id": order_id or str(uuid.uuid4()),
        "customer_id": str(uuid.uuid4()),
        "amount": 42.0,
        "card_number": "4242424242420000",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _process_message(db, message: dict, mock_publish: AsyncMock) -> bool:
    """Execute the same guard → route → mark → commit sequence as start_consumer.

    Returns True if the event was handled (not skipped as duplicate).
    """
    import asyncio  # pylint: disable=import-outside-toplevel

    event_id = message.get("event_id")
    event_type = message.get("event_type")

    if event_id and is_event_processed(db, event_id):
        return False

    with patch("app.kafka_consumer.publish_event", mock_publish):
        handled = asyncio.run(_route_event(event_type, message, db))

    if not handled:
        return False

    if event_id:
        mark_event_processed(db, event_id, "orders")
    db.commit()
    return True


@pytest.mark.usefixtures("db")
class TestDurableIdempotency:
    """Tests that prove business write + dedup marker are atomic."""

    def test_duplicate_event_blocked_after_restart(self, db):
        """Replaying the same event_id after a simulated restart must not duplicate.

        Uses the same guard → route → mark → commit sequence as the consumer loop.
        A 'restart' is simulated by using the same DB (durable) with a fresh call.
        """
        event_id = str(uuid.uuid4())
        message = _make_order_message(event_id)
        mock_publish = AsyncMock()

        # First processing — should create payment + dedup marker
        handled = _process_message(db, message, mock_publish)
        assert handled is True
        assert db.query(Payment).count() == 1
        assert mock_publish.call_count == 1
        assert is_event_processed(db, event_id) is True

        # Second processing (simulated restart — same DB, fresh call)
        mock_publish.reset_mock()
        handled = _process_message(db, message, mock_publish)
        assert handled is False
        assert db.query(Payment).count() == 1
        assert mock_publish.call_count == 0

    def test_atomicity_rollback_leaves_neither_payment_nor_marker(self, db):
        """If an error prevents commit, neither Payment nor ProcessedEvent persists.

        Injects a failure after route but before commit to prove the two
        writes are in the same transaction — rollback removes both.
        """
        import asyncio  # pylint: disable=import-outside-toplevel

        event_id = str(uuid.uuid4())
        message = _make_order_message(event_id)
        mock_publish = AsyncMock()

        # Run business logic (flush, no commit)
        with patch("app.kafka_consumer.publish_event", mock_publish):
            asyncio.run(_route_event("OrderCreated", message, db))

        # Add marker (flush, no commit) — then simulate crash via rollback
        mark_event_processed(db, event_id, "orders")
        db.rollback()

        # Neither the Payment nor the dedup marker survived the rollback
        assert db.query(Payment).count() == 0
        assert db.query(ProcessedEvent).count() == 0
        assert is_event_processed(db, event_id) is False


def test_is_event_processed_returns_false_for_new_event(db):
    """An event_id not in processed_events should return False."""
    assert is_event_processed(db, str(uuid.uuid4())) is False


def test_mark_and_check_event_processed(db):
    """mark_event_processed should make is_event_processed return True."""
    event_id = str(uuid.uuid4())
    mark_event_processed(db, event_id, "orders")
    db.commit()
    assert is_event_processed(db, event_id) is True


def test_processed_event_persists_columns(db):
    """ProcessedEvent row should have the correct event_id and topic."""
    event_id = str(uuid.uuid4())
    mark_event_processed(db, event_id, "couriers")
    db.commit()

    row = db.query(ProcessedEvent).filter_by(event_id=event_id).first()
    assert row is not None
    assert row.topic == "couriers"
    assert row.processed_at is not None

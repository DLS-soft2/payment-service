import asyncio
import json
import logging
from datetime import datetime, timezone
from uuid import UUID

from aiokafka import AIOKafkaConsumer
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models import Payment, ProcessedEvent
from app.events import (
    OrderCreated, PaymentAuthorized, PaymentFailed,
    RestaurantRejected, CourierAssignmentFailed, PaymentRefunded,
)
from app.kafka_producer import publish_event

logger = logging.getLogger(__name__)


def is_event_processed(db: Session, event_id: str) -> bool:
    """Check if an event has already been processed (idempotency guard)."""
    return db.query(ProcessedEvent).filter_by(event_id=event_id).first() is not None


def mark_event_processed(db: Session, event_id: str, topic: str) -> None:
    """Record that an event has been processed."""
    db.add(ProcessedEvent(event_id=event_id, topic=topic))


def simulate_payment(amount: float, card_number: str) -> tuple[bool, str]:
    """
    Simulate payment processing based on the card number.

    Works like Stripe's test mode — specific card endings
    produce specific outcomes, so results are predictable
    and controllable from the frontend.

    Test card rules (based on last 4 digits):
      - Ends in 0000: Always succeeds (default test card)
      - Ends in 9999: Declined — insufficient funds
      - Ends in 5555: Declined — card expired
      - Ends in 1111: Declined — card reported stolen
      - Anything else: Succeeds

    Business rules (applied regardless of card):
      - Amount over 10000: Always fails (limit exceeded)
      - Amount of 0 or negative: Always fails (invalid amount)
    """
    # Business rule checks first
    if amount <= 0:
        return False, "Invalid amount"

    if amount > 10000:
        return False, "Amount exceeds maximum limit"

    # Card-based simulation using last 4 digits
    last_four = card_number[-4:] if len(card_number) >= 4 else card_number

    match last_four:
        case "9999":
            return False, "Insufficient funds"
        case "5555":
            return False, "Card expired"
        case "1111":
            return False, "Card reported stolen"
        case _:
            return True, "Payment authorized"


def process_payment(order_event: OrderCreated, db: Session) -> Payment:
    """
    Process a payment for an order and save it to the database.

    Args:
        order_event: The OrderCreated event from Kafka
        db: Database session

    Returns:
        The created Payment record
    """
    success, reason = simulate_payment(order_event.amount, order_event.card_number)

    payment = Payment(
        order_id=order_event.order_id,
        amount=order_event.amount,
        status="AUTHORIZED" if success else "FAILED",
    )
    db.add(payment)
    db.flush()
    db.refresh(payment)

    logger.info(
        "Payment %s for order %s: %s",
        payment.status,
        order_event.order_id,
        reason,
    )

    return payment


async def handle_order_created(message_value: dict, db: Session | None = None):
    """Handle a single OrderCreated event.

    Parses the event, processes the payment, and publishes the result.
    When db is provided, the caller owns the session lifecycle.
    """
    try:
        order_event = OrderCreated(**message_value)
    except Exception as exc:
        logger.error("Invalid OrderCreated event: %s — %s", message_value, exc)
        return

    owns_session = db is None
    if owns_session:
        db = SessionLocal()
    try:
        payment = process_payment(order_event, db)

        now = datetime.now(timezone.utc)

        if payment.status == "AUTHORIZED":
            event = PaymentAuthorized(
                order_id=order_event.order_id,
                customer_id=order_event.customer_id,
                restaurant_id=order_event.restaurant_id,
                payment_id=payment.id,
                amount=payment.amount,
                delivery_address=order_event.delivery_address,
                timestamp=now,
            )
        else:
            event = PaymentFailed(
                order_id=order_event.order_id,
                customer_id=order_event.customer_id,
                reason="Payment declined",
                timestamp=now,
            )

        await publish_event(settings.kafka_topic_payments, event.model_dump())

    finally:
        if owns_session:
            db.commit()
            db.close()


def refund_payment(order_id: UUID, reason: str, db: Session) -> Payment | None:
    """Look up the AUTHORIZED payment for an order and transition it to REFUNDED.

    Returns the updated Payment if refunded, or None if skipped
    (no payment found, or payment not in AUTHORIZED status).
    """
    payment = db.query(Payment).filter(Payment.order_id == order_id).first()

    if not payment:
        logger.warning("No payment found for order %s — skipping refund", order_id)
        return None

    if payment.status != "AUTHORIZED":
        logger.info(
            "Payment %s for order %s is '%s', not AUTHORIZED — skipping refund",
            payment.id, order_id, payment.status,
        )
        return None

    payment.status = "REFUNDED"
    db.flush()
    db.refresh(payment)

    logger.info("Payment %s for order %s refunded: %s", payment.id, order_id, reason)
    return payment


async def handle_refund_event(
    event_model: RestaurantRejected | CourierAssignmentFailed,
    reason_prefix: str,
    db: Session | None = None,
) -> None:
    """Handle a failure event that triggers a payment refund.

    Shared handler for RestaurantRejected and CourierAssignmentFailed events.
    Looks up the payment, refunds it, and publishes PaymentRefunded.
    When db is provided, the caller owns the session lifecycle.
    """
    reason = f"{reason_prefix}: {event_model.reason}"

    owns_session = db is None
    if owns_session:
        db = SessionLocal()
    try:
        payment = refund_payment(
            order_id=event_model.order_id,
            reason=reason,
            db=db,
        )
        if not payment:
            return

        refund_event = PaymentRefunded(
            order_id=event_model.order_id,
            customer_id=event_model.customer_id,
            payment_id=payment.id,
            amount=payment.amount,
            reason=reason,
            timestamp=datetime.now(timezone.utc),
        )
        await publish_event(settings.kafka_topic_payments, refund_event.model_dump())
    finally:
        if owns_session:
            db.commit()
            db.close()


_EVENT_ROUTING: dict[str, tuple[type, str]] = {
    "RestaurantRejected": (RestaurantRejected, "Restaurant rejected order"),
    "CourierAssignmentFailed": (CourierAssignmentFailed, "Courier assignment failed"),
}


async def _route_event(event_type: str, value: dict, db: Session) -> bool:
    """Route an incoming message to the correct handler.

    Returns True if the event was handled, False if the event type is unknown.
    The caller provides the DB session so dedup and business logic share a transaction.
    """
    if event_type == "OrderCreated":
        await handle_order_created(value, db=db)
        return True

    routing = _EVENT_ROUTING.get(event_type)
    if not routing:
        return False

    model_cls, reason_prefix = routing
    try:
        event = model_cls(**value)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.error("Invalid %s event: %s — %s", event_type, value, exc)
        return False

    await handle_refund_event(event, reason_prefix, db=db)
    return True


async def start_consumer():
    """Start the multi-topic Kafka consumer loop.

    Subscribes to orders, restaurants, and couriers topics.
    Uses group_id 'payment-service-group' for horizontal scaling.
    Retries connection up to 10 times with 3-second intervals.
    """
    topics = [
        settings.kafka_topic_orders,
        settings.kafka_topic_restaurants,
        settings.kafka_topic_couriers,
    ]

    consumer = AIOKafkaConsumer(
        *topics,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id="payment-service-group",
        auto_offset_reset="earliest",
    )

    for attempt in range(1, 11):
        try:
            await consumer.start()
            logger.info("Kafka consumer started — listening on %s", topics)
            break
        except Exception as exc:
            logger.warning(
                "Kafka not ready for consumer (attempt %d/10): %s", attempt, exc
            )
            if attempt == 10:
                raise
            await asyncio.sleep(3)

    try:
        async for message in consumer:
            try:
                value = json.loads(message.value.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                logger.warning("Skipping invalid message at offset %d: %s", message.offset, exc)
                continue

            logger.info(
                "Received message from topic '%s' partition %d offset %d",
                message.topic, message.partition, message.offset,
            )

            event_type = value.get("event_type")
            event_id = value.get("event_id")

            db = SessionLocal()
            try:
                # Idempotency guard: skip already-processed events (DB-backed)
                if event_id and is_event_processed(db, event_id):
                    logger.info("Event %s already processed — skipping", event_id)
                    continue

                handled = await _route_event(event_type, value, db)
                if not handled:
                    logger.warning("Unknown event type: %s — skipping", event_type)
                    continue

                if event_id:
                    mark_event_processed(db, event_id, message.topic)
                db.commit()
            finally:
                db.close()

    except asyncio.CancelledError:
        logger.info("Consumer task was cancelled")
    except Exception as exc:
        logger.error("Consumer crashed with error: %s", exc, exc_info=True)
    finally:
        await consumer.stop()
        logger.info("Kafka consumer stopped")

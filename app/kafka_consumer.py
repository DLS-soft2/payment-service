"""
Kafka consumer for the Payment Service.

Listens on the 'orders' topic for OrderCreated events.
When an order comes in, it:
  1. Validates the event data
  2. Simulates payment processing
  3. Saves the payment record to PostgreSQL
  4. Publishes the result (PaymentAuthorized or PaymentFailed)
     to the 'payments' topic

The consumer runs as a background task — it loops forever,
picking up new messages as they arrive. Think of it as a
worker that sits by the mailbox and processes each letter.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone

from aiokafka import AIOKafkaConsumer
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models import Payment
from app.events import OrderCreated, PaymentAuthorized, PaymentFailed
from app.kafka_producer import publish_event

logger = logging.getLogger(__name__)


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
    db.commit()
    db.refresh(payment)

    logger.info(
        "Payment %s for order %s: %s",
        payment.status,
        order_event.order_id,
        reason,
    )

    return payment


async def handle_order_created(message_value: dict):
    """
    Handle a single OrderCreated event.

    This is where the core business logic lives:
    1. Parse and validate the event
    2. Process the payment
    3. Publish the result to the payments topic
    """
    # Parse the raw dict into our typed event model
    try:
        order_event = OrderCreated(**message_value)
    except Exception as exc:
        logger.error("Invalid OrderCreated event: %s — %s", message_value, exc)
        return

    # Process payment (uses its own DB session)
    db = SessionLocal()
    try:
        payment = process_payment(order_event, db)

        # Publish the result to the payments topic
        now = datetime.now(timezone.utc)

        if payment.status == "AUTHORIZED":
            event = PaymentAuthorized(
                order_id=order_event.order_id,
                payment_id=payment.id,
                amount=payment.amount,
                timestamp=now,
            )
        else:
            event = PaymentFailed(
                order_id=order_event.order_id,
                reason="Payment declined",
                timestamp=now,
            )

        await publish_event(settings.kafka_topic_payments, event.model_dump())

    finally:
        db.close()


async def start_consumer():
    """
    Start the Kafka consumer loop.

    This runs forever as a background task. It:
    1. Connects to Kafka
    2. Subscribes to the 'orders' topic
    3. Loops over incoming messages
    4. Calls handle_order_created for each OrderCreated event

    The group_id ensures that if you run multiple instances of
    Payment Service, each message is only processed by ONE instance.
    Kafka distributes messages across consumers in the same group.
    This is how you scale horizontally — just start more instances.
    """
    consumer = AIOKafkaConsumer(
        settings.kafka_topic_orders,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id="payment-service-group",
        auto_offset_reset="earliest",
    )

    # Retry connection — Kafka may still be starting
    for attempt in range(1, 11):
        try:
            await consumer.start()
            logger.info("Kafka consumer started — listening on '%s'", settings.kafka_topic_orders)
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
            # Manually deserialize — skip invalid messages instead of crashing
            try:
                value = json.loads(message.value.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                logger.warning("Skipping invalid message at offset %d: %s", message.offset, exc)
                continue

            logger.info(
                "Received message from topic '%s' partition %d offset %d",
                message.topic,
                message.partition,
                message.offset,
            )

            # Only process OrderCreated events (ignore others)
            event_type = value.get("event_type")
            if event_type == "OrderCreated":
                await handle_order_created(value)
            else:
                logger.warning("Unknown event type: %s — skipping", event_type)

    except asyncio.CancelledError:
        logger.info("Consumer task was cancelled")
    except Exception as exc:
        logger.error("Consumer crashed with error: %s", exc, exc_info=True)
    finally:
        await consumer.stop()
        logger.info("Kafka consumer stopped")
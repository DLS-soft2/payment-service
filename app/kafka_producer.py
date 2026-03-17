"""
Kafka producer for the Payment Service.

Sends payment result events to the 'payments' topic.
Other services (Order Service, Notification Service) consume
these events to react to payment outcomes.

The producer is started once when the app boots up (in main.py's
lifespan) and reused for all messages. Creating a new producer
per message would be wasteful — like opening a new phone line
for every text message instead of keeping one connection open.
"""

import asyncio
import json
import logging

from aiokafka import AIOKafkaProducer

from app.config import settings

logger = logging.getLogger(__name__)

# Module-level reference — set during app startup, used everywhere
producer: AIOKafkaProducer | None = None


async def start_producer():
    """
    Start the Kafka producer with retry logic.

    Kafka might not be ready when the service starts, so we
    retry a few times before giving up. This is a common pattern
    in microservices — you can't control startup order.
    """
    global producer  # pylint: disable=global-statement
    producer = AIOKafkaProducer(
        bootstrap_servers=settings.kafka_bootstrap_servers,
        value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
    )

    # Retry up to 10 times with 3 seconds between attempts
    for attempt in range(1, 11):
        try:
            await producer.start()
            logger.info("Kafka producer started")
            return
        except Exception as exc:
            logger.warning(
                "Kafka not ready (attempt %d/10): %s", attempt, exc
            )
            if attempt == 10:
                raise
            await asyncio.sleep(3)


async def stop_producer():
    """Stop the Kafka producer gracefully. Called during app shutdown."""
    global producer  # pylint: disable=global-statement
    if producer:
        await producer.stop()
        logger.info("Kafka producer stopped")
        producer = None


async def publish_event(topic: str, event_data: dict):
    """
    Publish an event to a Kafka topic.

    Args:
        topic: The Kafka topic name (e.g. "payments")
        event_data: Dictionary that will be serialized to JSON

    The order_id is used as the message key. This guarantees that
    all events for the same order go to the same Kafka partition,
    which means they are processed in order. Without a key, events
    could end up on different partitions and be consumed out of order.
    """
    if not producer:
        logger.error("Producer not started — cannot publish event")
        return

    # Use order_id as the partition key
    key = str(event_data.get("order_id", "")).encode("utf-8")

    await producer.send_and_wait(
        topic=topic,
        value=event_data,
        key=key,
    )
    logger.info("Published %s to topic '%s'", event_data.get("event_type"), topic)

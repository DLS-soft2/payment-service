"""
Payment Service — FastAPI application entry point.

This service handles payment processing for the DLS-2 food delivery platform.
It consumes OrderCreated events from Kafka, processes payments, and publishes
PaymentAuthorized or PaymentFailed events back to Kafka.

The REST API is read-only — payments are created via Kafka events, not HTTP.
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app import database
from app.database import Base
from app.routers import payments
from app.kafka_producer import start_producer, stop_producer
from app.kafka_consumer import start_consumer

# Configure logging so we can see what's happening
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Runs on startup and shutdown.

    Startup:
      1. Create database tables
      2. Start the Kafka producer (for sending payment results)
      3. Start the Kafka consumer as a background task (for receiving orders)

    Shutdown:
      1. Cancel the consumer background task
      2. Stop the Kafka producer

    The consumer runs as an asyncio task — it loops in the background
    while FastAPI handles HTTP requests on the main thread. Both can
    run concurrently because they're async (non-blocking).
    """
    # 1. Create database tables
    Base.metadata.create_all(bind=database.engine)
    logger.info("Database tables created")

    # 2. Start Kafka producer
    await start_producer()

    # 3. Start Kafka consumer as a background task
    # asyncio.create_task runs the consumer loop concurrently
    # with the FastAPI server — neither blocks the other
    consumer_task = asyncio.create_task(start_consumer())
    logger.info("Kafka consumer background task started")

    yield  # App is running — handles HTTP requests here

    # Shutdown: clean up resources
    consumer_task.cancel()
    try:
        await consumer_task
    except asyncio.CancelledError:
        logger.info("Kafka consumer task cancelled")

    await stop_producer()
    logger.info("Shutdown complete")


app = FastAPI(
    title="Payment Service",
    description="Handles payment processing for the DLS-2 food delivery platform",
    version=settings.service_version,
    lifespan=lifespan,
)

# Register the REST router
app.include_router(payments.router)


@app.get("/")
def root():
    """Service info endpoint."""
    return {
        "service": settings.service_name,
        "version": settings.service_version,
    }


@app.get("/health")
def health():
    """Health check for monitoring and container orchestration."""
    return {"status": "healthy"}

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

from app.config import settings
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
async def lifespan(_app: FastAPI):
    """
    Start Kafka producer and consumer on startup; stop on shutdown.

    The consumer runs as an asyncio task — it loops in the background
    while FastAPI handles HTTP requests on the main thread.
    """
    await start_producer()

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
Instrumentator().instrument(app).expose(app)

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

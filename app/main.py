"""
Payment Service — FastAPI application entry point.

This service handles payment processing for the DLS-2 food delivery platform.
It consumes OrderCreated events from Kafka, processes payments, and publishes
PaymentAuthorized or PaymentFailed events back to Kafka.

The REST API is read-only — payments are created via Kafka events, not HTTP.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.database import engine, Base
from app.routers import payments


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Runs on startup and shutdown.

    Startup: creates database tables if they don't exist.
    Shutdown: (will later disconnect Kafka consumers gracefully)
    """
    # Create all tables defined in models.py
    Base.metadata.create_all(bind=engine)
    yield
    # Shutdown logic will go here when we add Kafka


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

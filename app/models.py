import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Float, DateTime, Uuid, func

from app.database import Base


class Payment(Base):
    """Represents a single payment attempt for an order."""

    __tablename__ = "payments"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id = Column(Uuid(as_uuid=True), nullable=False, index=True)
    amount = Column(Float, nullable=False)
    status = Column(String, nullable=False, default="PENDING")
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class ProcessedEvent(Base):
    """Tracks consumed Kafka event IDs for idempotency."""

    __tablename__ = "processed_events"

    event_id = Column(String, primary_key=True)
    topic = Column(String, nullable=False)
    processed_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),  # pylint: disable=not-callable
    )

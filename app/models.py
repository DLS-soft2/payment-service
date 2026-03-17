"""
Database table definitions for the Payment Service.

Each payment is linked to an order via order_id. The status field
tracks where the payment is in its lifecycle:
  PENDING → AUTHORIZED (success) or FAILED (declined/error)
  AUTHORIZED → CAPTURED (money transferred) or REFUNDED
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Float, DateTime
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class Payment(Base):
    """Represents a single payment attempt for an order."""

    __tablename__ = "payments"

    # UUID primary key — avoids sequential IDs that leak info
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Which order this payment belongs to
    order_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Payment amount in the smallest currency unit
    amount = Column(Float, nullable=False)

    # Current status: PENDING, AUTHORIZED, FAILED, CAPTURED, REFUNDED
    status = Column(String, nullable=False, default="PENDING")

    # Timestamps for auditing
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

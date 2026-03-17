"""
Pydantic models for request validation and response serialization.

These are NOT database models — they define the shape of data
that flows through the REST API. FastAPI uses them to:
  1. Validate incoming request bodies automatically
  2. Serialize responses to JSON
  3. Generate OpenAPI/Swagger documentation
"""

from uuid import UUID
from datetime import datetime

from pydantic import BaseModel


class PaymentResponse(BaseModel):
    """What the API returns when you fetch a payment."""

    id: UUID
    order_id: UUID
    amount: float
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True  # Allows converting SQLAlchemy models directly

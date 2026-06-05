from uuid import UUID, uuid4
from datetime import datetime

from pydantic import BaseModel, Field


class OrderCreated(BaseModel):
    """Consumed from the 'orders' topic when a customer places a new order."""

    event_id: UUID = Field(default_factory=uuid4)
    event_type: str = "OrderCreated"
    order_id: UUID
    customer_id: UUID
    restaurant_id: UUID | None = None
    amount: float
    card_number: str = "4242424242420000"
    timestamp: datetime


class PaymentAuthorized(BaseModel):
    """Produced to the 'payments' topic when payment succeeds."""

    event_id: UUID = Field(default_factory=uuid4)
    event_type: str = "PaymentAuthorized"
    order_id: UUID
    customer_id: UUID
    restaurant_id: UUID | None = None
    payment_id: UUID
    amount: float
    timestamp: datetime


class PaymentFailed(BaseModel):
    """Produced to the 'payments' topic when payment fails."""

    event_id: UUID = Field(default_factory=uuid4)
    event_type: str = "PaymentFailed"
    order_id: UUID
    customer_id: UUID | None = None
    reason: str
    timestamp: datetime

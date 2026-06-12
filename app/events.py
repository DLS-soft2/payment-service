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
    delivery_address: str | None = None
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
    delivery_address: str | None = None
    timestamp: datetime


class PaymentFailed(BaseModel):
    """Produced to the 'payments' topic when payment fails."""

    event_id: UUID = Field(default_factory=uuid4)
    event_type: str = "PaymentFailed"
    order_id: UUID
    customer_id: UUID | None = None
    reason: str
    timestamp: datetime


class RestaurantRejected(BaseModel):
    """Consumed from the 'restaurants' topic when a restaurant rejects an order."""

    event_id: UUID = Field(default_factory=uuid4)
    event_type: str = "RestaurantRejected"
    order_id: UUID
    customer_id: UUID
    restaurant_id: UUID
    reason: str
    timestamp: datetime


class CourierAssignmentFailed(BaseModel):
    """Consumed from the 'couriers' topic when no courier can be assigned."""

    event_id: UUID = Field(default_factory=uuid4)
    event_type: str = "CourierAssignmentFailed"
    order_id: UUID
    customer_id: UUID
    restaurant_id: UUID
    reason: str
    timestamp: datetime


class PaymentRefunded(BaseModel):
    """Produced to the 'payments' topic when a payment is refunded."""

    event_id: UUID = Field(default_factory=uuid4)
    event_type: str = "PaymentRefunded"
    order_id: UUID
    customer_id: UUID
    payment_id: UUID
    amount: float
    reason: str
    timestamp: datetime

"""
Kafka event schemas for the Payment Service.

These define the structure of messages that flow through Kafka.
Think of them as contracts between services — Order Service and
Payment Service agree on what an OrderCreated event looks like,
even though they never talk directly to each other.

Events IN (consumed from "orders" topic):
  - OrderCreated: a new order has been placed, payment is needed

Events OUT (produced to "payments" topic):
  - PaymentAuthorized: payment succeeded, order can proceed
  - PaymentFailed: payment failed, order should be cancelled
"""

from uuid import UUID
from datetime import datetime

from pydantic import BaseModel


class OrderCreated(BaseModel):
    """
    Event consumed from the 'orders' topic.

    Published by Order Service when a customer places a new order.
    Contains the minimum info Payment Service needs to process payment.
    """
    event_type: str = "OrderCreated"
    order_id: UUID
    customer_id: UUID
    amount: float
    card_number: str = "4242424242420000"  # Default to a card that always succeeds
    timestamp: datetime


class PaymentAuthorized(BaseModel):
    """
    Event produced to the 'payments' topic on success.

    Order Service consumes this and updates the order status to PAID.
    Restaurant Service may also consume it to start preparing the food.
    """
    event_type: str = "PaymentAuthorized"
    order_id: UUID
    payment_id: UUID
    amount: float
    timestamp: datetime


class PaymentFailed(BaseModel):
    """
    Event produced to the 'payments' topic on failure.

    Order Service consumes this and updates the order status to CANCELLED.
    """
    event_type: str = "PaymentFailed"
    order_id: UUID
    reason: str
    timestamp: datetime

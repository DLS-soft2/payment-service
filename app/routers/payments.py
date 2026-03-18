"""
REST endpoints for the Payment Service.

Note: there is no POST endpoint to create payments.
Payments are created automatically when the service receives
an OrderCreated event from Kafka. The REST API is read-only —
it lets other services and the frontend check payment status.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Payment
from app.schemas import PaymentResponse

router = APIRouter(prefix="/v1/payments", tags=["payments"])


@router.get("/", response_model=list[PaymentResponse])
def list_payments(skip: int = 0, limit: int = 20, db: Session = Depends(get_db)):
    """List all payments with pagination."""
    payments = db.query(Payment).offset(skip).limit(limit).all()
    return payments


@router.get("/{payment_id}", response_model=PaymentResponse)
def get_payment(payment_id: UUID, db: Session = Depends(get_db)):
    """Get a specific payment by its ID."""
    payment = db.query(Payment).filter(Payment.id == payment_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    return payment


@router.get("/order/{order_id}", response_model=list[PaymentResponse])
def get_payments_by_order(order_id: UUID, db: Session = Depends(get_db)):
    """Get all payments for a specific order."""
    payments = db.query(Payment).filter(Payment.order_id == order_id).all()
    return payments

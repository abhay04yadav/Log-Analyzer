"""HTTP endpoints of the payment service."""
from fastapi import APIRouter

from payment.repository import PaymentRepository

router = APIRouter()
repo = PaymentRepository()



@router.post("/payments")
def create_payment(body: dict):
    result = repo.charge_card(body["order_id"], body["amount"], body["card_token"])
    return result

"""Checkout flow: reserve stock, take payment, confirm the order."""
import httpx

PAYMENT_URL = "http://payment-service:8000/payments"


class PaymentServiceError(Exception):
    pass


def place_order(order: dict) -> dict:
    total = sum(item["price"] * item["qty"] for item in order["items"])
    response = httpx.post(PAYMENT_URL, json={"order_id": order["id"], "amount": total,
                                             "card_token": order["card_token"]}, timeout=5)
    if response.status_code >= 500:
        raise PaymentServiceError(f"payment-service returned {response.status_code}")
    return {"order_id": order["id"], "status": "confirmed"}

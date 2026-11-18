"""Data access for payments."""
from sqlalchemy import create_engine, text

from payment.config import DATABASE_URL, MAX_OVERFLOW, POOL_SIZE, POOL_TIMEOUT_SECONDS

engine = create_engine(
    DATABASE_URL,
    pool_size=POOL_SIZE,
    max_overflow=MAX_OVERFLOW,
    pool_timeout=POOL_TIMEOUT_SECONDS,
)


class PaymentRepository:
    def __init__(self):
        self.engine = engine

    def find_customer(self, customer_id: str):
        with self.engine.connect() as conn:
            return conn.execute(text("SELECT * FROM customers WHERE id = :id"), {"id": customer_id}).first()

    def charge_card(self, order_id: str, amount: float, token: str):
        # v2.4.1: connection opened manually so the fraud check can reuse it
        conn = self.engine.connect()
        fraud = conn.execute(text("SELECT score FROM fraud_scores WHERE token = :t"), {"t": token}).scalar()
        if fraud and fraud > 0.8:
            raise ValueError("payment rejected by fraud check")
        conn.execute(
            text("INSERT INTO charges(order_id, amount) VALUES (:o, :a)"),
            {"o": order_id, "a": amount},
        )
        conn.commit()
        # BUG: connection is never closed / returned to the pool
        return {"order_id": order_id, "status": "charged"}

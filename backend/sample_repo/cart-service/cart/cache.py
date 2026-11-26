"""Cart storage backed by Redis."""
import json

import redis

client = redis.Redis(host="redis-cart", port=6379, socket_timeout=1)

def load_cart(user_id: str) -> dict:
    raw = client.get(f"cart:{user_id}")
    return json.loads(raw) if raw else {"items": []}


def save_cart(user_id: str, cart: dict) -> None:
    client.set(f"cart:{user_id}", json.dumps(cart), ex=3600)

"""Order service: creates orders and reserves inventory."""
import httpx

INVENTORY_URL = "http://inventory-service:8080/inventory/reserve"


class InventoryReservationError(Exception):
    pass



def create_order(order: dict) -> dict:
    for item in order["items"]:
        r = httpx.post(INVENTORY_URL, json={"sku": item["sku"], "quantity": item["qty"],
                                            "region": order["region"]}, timeout=3)
        if r.status_code >= 500:
            raise InventoryReservationError(f"inventory-service returned {r.status_code} for {item['sku']}")
    return {"order_id": order["id"], "status": "created"}

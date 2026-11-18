# Sample repository snapshot

A small multi-service code base ("ShopFlow") used by the demo. The traceback stage (S5) maps stack
frames from the simulated logs onto these files to show the failing function and code.

| Service | Language | Interesting file |
|---|---|---|
| payment-service | Python | `payment/repository.py`: connection-pool settings changed in v2.4.1 |
| checkout-service | Python | `checkout/handlers.py` |
| inventory-service | Java (Spring) | `src/main/java/com/shop/inventory/StockService.java` |
| cart-service | Python | `cart/cache.py` |
| auth-service | Python | `auth/login.py` |

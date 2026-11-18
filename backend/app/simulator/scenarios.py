"""Realistic log generator for the "ShopFlow" demo system.

Services:  api-gateway -> checkout-service -> payment-service
           api-gateway -> order-service -> inventory-service (Java)
           api-gateway -> cart-service -> redis
           api-gateway -> auth-service
Each service logs in a different format (JSON, logfmt, plain text with multi-line stack traces),
which exercises the normaliser.  Every scenario returns a list of steps:
    (offset_seconds, "log", item)          item = dict (JSON log) or str (raw line)
    (offset_seconds, "deploy", dict)       deployment record
"""
import json
import random
import uuid
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path

from app.core.config import get_settings

SCENARIOS = {
    "db_pool_exhaustion": {
        "title": "Payment DB connection pool exhausted after deployment",
        "description": "payment-service v2.4.1 leaks DB connections; checkout and the gateway start failing.",
        "expected_root_cause": "payment-service: QueuePool exhausted in payment/repository.py charge_card",
    },
    "inventory_null_pointer": {
        "title": "Java NullPointerException in inventory-service",
        "description": "inventory-service v1.8.0 has no warehouse for region ap-south-2; orders fail.",
        "expected_root_cause": "inventory-service: NullPointerException in StockService.reserve",
    },
    "cache_outage": {
        "title": "Redis cache outage (known error)",
        "description": "cart-service cannot reach Redis; matched by the known-error playbook.",
        "expected_root_cause": "cart-service: Redis connection refused",
    },
    "brute_force_login": {
        "title": "Brute-force login attack",
        "description": "Repeated failed logins from one IP, followed by a successful login.",
        "expected_root_cause": "203.0.113.45 guessing passwords on auth-service",
    },
}


def _iso(t: datetime) -> str:
    return t.isoformat(timespec="milliseconds") + "Z"


def _tid() -> str:
    return uuid.uuid4().hex


def _sid() -> str:
    return uuid.uuid4().hex[:16]


@lru_cache(maxsize=64)
def line_of(rel_path: str, needle: str, default: int) -> int:
    """Line number of `needle` in the sample repository (keeps stack traces in sync with the code)."""
    try:
        for i, ln in enumerate(Path(get_settings().code_repo_path, rel_path).read_text("utf-8").splitlines(), 1):
            if needle in ln:
                return i
    except OSError:
        pass
    return default


# ---------------------------------------------------------------- per-service log writers
def gw_line(t, level, msg, trace, span):
    return f"{_iso(t)} {level} [api-gateway] {msg} trace_id={trace} span_id={span}"


def logfmt(t, level, service, msg, trace=None, span=None, parent=None, **kw):
    parts = [f"ts={_iso(t)}", f"level={level}", f"service={service}"]
    for k, v in (("trace_id", trace), ("span_id", span), ("parent_span_id", parent)):
        if v:
            parts.append(f"{k}={v}")
    parts += [f"{k}={json.dumps(str(v))}" for k, v in kw.items()]
    parts.append(f"msg={json.dumps(msg)}")
    return " ".join(parts)


def jlog(t, level, service, msg, trace=None, span=None, parent=None, **extra):
    d = {"timestamp": _iso(t), "level": level, "service": service, "message": msg}
    if trace:
        d.update(trace_id=trace, span_id=span, parent_span_id=parent)
    d.update(extra)
    return d


# ---------------------------------------------------------------- healthy traffic
def healthy_checkout(t):
    tr, g, c, p = _tid(), _sid(), _sid(), _sid()
    ms = random.randint(90, 240)
    return [
        (t, "log", jlog(t + timedelta(milliseconds=30), "INFO", "payment-service", "Card charged",
                        tr, p, c, logger="payment.api", amount=round(random.uniform(10, 300), 2))),
        (t, "log", logfmt(t + timedelta(milliseconds=ms - 20), "info", "checkout-service", "Order placed",
                          tr, c, g, order_id=f"ORD-{random.randint(10000, 99999)}")),
        (t, "log", gw_line(t + timedelta(milliseconds=ms), "INFO", f"POST /api/checkout 200 {ms}ms", tr, g)),
    ]


def healthy_order(t):
    tr, g, o, i = _tid(), _sid(), _sid(), _sid()
    return [
        (t, "log", f"{_iso(t + timedelta(milliseconds=15))} INFO [inventory-service] c.s.i.StockService - "
                   f"Reserved 1 x SKU-{random.randint(1000, 1999)} trace_id={tr} span_id={i} parent_span_id={o}"),
        (t, "log", jlog(t + timedelta(milliseconds=40), "INFO", "order-service", "Order created", tr, o, g,
                        logger="orders.service")),
        (t, "log", gw_line(t + timedelta(milliseconds=55), "INFO", "POST /api/orders 201 55ms", tr, g)),
    ]


def healthy_cart(t):
    tr, g, c = _tid(), _sid(), _sid()
    return [
        (t, "log", jlog(t + timedelta(milliseconds=4), "INFO", "cart-service", "Cart loaded", tr, c, g,
                        logger="cart.cache", peer_service="redis")),
        (t, "log", gw_line(t + timedelta(milliseconds=9), "INFO", "GET /api/cart 200 9ms", tr, g)),
    ]


def healthy_login(t):
    users = ["priya", "rahul", "neha", "arjun", "kavya"]
    ip = f"10.0.{random.randint(1, 9)}.{random.randint(2, 250)}"
    u = random.choice(users)
    return [(t, "log", jlog(t, "INFO", "auth-service", f"Login succeeded for user {u} from {ip}",
                            logger="auth.login", event="auth_success", username=u, client_ip=ip))]


HEALTHY = [healthy_checkout, healthy_order, healthy_cart, healthy_login]


def background(start, duration, every=0.6):
    out, t = [], 0.0
    while t < duration:
        out += [(t, k, v) for _, k, v in random.choice(HEALTHY)(start + timedelta(seconds=t))]
        t += every * random.uniform(0.6, 1.4)
    return out


# ---------------------------------------------------------------- scenarios
def db_pool_exhaustion(start: datetime) -> list:
    repo, api = "payment-service/payment/repository.py", "payment-service/payment/api.py"
    l_conn = line_of(repo, "conn = self.engine.connect()", 23)
    l_api = line_of(api, "repo.charge_card(", 12)
    steps = [(0, "deploy", dict(service="payment-service", version="v2.4.1", commit="a1b2c3d",
                                author="dev-team", ts=_iso(start - timedelta(minutes=4)),
                                description="Reuse DB connection for fraud check; reduce pool size to 5",
                                changed_files=["payment/repository.py", "payment/config.py"]))]
    steps += background(start, 24)
    for t, used, waiting in ((3.0, 4, 0), (4.5, 5, 3), (6.0, 5, 9), (9.0, 5, 17)):
        steps.append((t, "log", jlog(start + timedelta(seconds=t), "WARN", "payment-service",
                                     f"Connection pool usage high: {used}/5 connections checked out, "
                                     f"{waiting} requests waiting", logger="payment.repository")))
    t = 6.0
    while t < 22:
        base = start + timedelta(seconds=t)
        tr, g, c, p = _tid(), _sid(), _sid(), _sid()
        stack = (
            "Traceback (most recent call last):\n"
            '  File "/usr/local/lib/python3.12/site-packages/starlette/routing.py", line 74, in app\n'
            "    response = await f(request)\n"
            f'  File "/app/payment/api.py", line {l_api}, in create_payment\n'
            '    result = repo.charge_card(body["order_id"], body["amount"], body["card_token"])\n'
            f'  File "/app/payment/repository.py", line {l_conn}, in charge_card\n'
            "    conn = self.engine.connect()\n"
            '  File "/usr/local/lib/python3.12/site-packages/sqlalchemy/engine/base.py", line 3278, in connect\n'
            "    return self._connection_cls(self)\n"
            '  File "/usr/local/lib/python3.12/site-packages/sqlalchemy/pool/impl.py", line 157, in _do_get\n'
            "    raise exc.TimeoutError(\n"
            "sqlalchemy.exc.TimeoutError: QueuePool limit of size 5 overflow 0 reached, "
            "connection timed out, timeout 3.00")
        steps += [
            (t, "log", jlog(base, "ERROR", "payment-service",
                            "Payment failed: QueuePool limit of size 5 overflow 0 reached, connection timed out",
                            tr, p, c, logger="payment.api", stack_trace=stack, order_id=f"ORD-{random.randint(10000, 99999)}")),
            (t, "log", logfmt(base + timedelta(milliseconds=12), "error", "checkout-service",
                              "PaymentServiceError: payment-service returned 503", tr, c, g,
                              error_type="PaymentServiceError")),
            (t, "log", gw_line(base + timedelta(milliseconds=20), "ERROR",
                               "POST /api/checkout 502 upstream checkout-service failed", tr, g)),
        ]
        t += random.uniform(0.35, 0.8)
    return steps


def inventory_null_pointer(start: datetime) -> list:
    svc = "inventory-service/src/main/java/com/shop/inventory/"
    l_npe = line_of(svc + "StockService.java", "warehouse.getStock(sku)", 18)
    l_ctl = line_of(svc + "InventoryController.java", "stockService.reserve(", 17)
    l_ord = line_of("order-service/orders/service.py", "raise InventoryReservationError", 16)
    steps = [(0, "deploy", dict(service="inventory-service", version="v1.8.0", commit="9f8e7d6",
                                author="dev-team", ts=_iso(start - timedelta(minutes=6)),
                                description="Route stock reservations to the regional warehouse",
                                changed_files=["src/main/java/com/shop/inventory/StockService.java"]))]
    steps += background(start, 22)
    t = 4.0
    while t < 20:
        base = start + timedelta(seconds=t)
        tr, g, o, i = _tid(), _sid(), _sid(), _sid()
        sku = f"SKU-{random.randint(1000, 1999)}"
        java = (f"{_iso(base)} ERROR [inventory-service] c.s.i.InventoryController - Request processing failed "
                f"trace_id={tr} span_id={i} parent_span_id={o}\n"
                'java.lang.NullPointerException: Cannot invoke "com.shop.inventory.Warehouse.getStock(String)" '
                'because "warehouse" is null\n'
                f"\tat com.shop.inventory.StockService.reserve(StockService.java:{l_npe})\n"
                f"\tat com.shop.inventory.InventoryController.reserve(InventoryController.java:{l_ctl})\n"
                "\tat org.springframework.web.method.support.InvocableHandlerMethod.doInvoke"
                "(InvocableHandlerMethod.java:255)\n"
                "\tat org.springframework.web.servlet.FrameworkServlet.service(FrameworkServlet.java:885)\n"
                "\tat java.base/java.lang.Thread.run(Thread.java:1583)")
        pystack = ("Traceback (most recent call last):\n"
                   f'  File "/app/orders/service.py", line {l_ord}, in create_order\n'
                   '    raise InventoryReservationError(f"inventory-service returned {r.status_code} ...")\n'
                   f"orders.service.InventoryReservationError: inventory-service returned 500 for {sku}")
        steps += [
            (t, "log", java),
            (t, "log", jlog(base + timedelta(milliseconds=9), "ERROR", "order-service",
                            f"InventoryReservationError: inventory-service returned 500 for {sku}", tr, o, g,
                            logger="orders.service", exception=pystack, region="ap-south-2")),
            (t, "log", gw_line(base + timedelta(milliseconds=14), "ERROR",
                               "POST /api/orders 500 upstream order-service failed", tr, g)),
        ]
        t += random.uniform(0.5, 1.1)
    return steps


def cache_outage(start: datetime) -> list:
    l_get = line_of("cart-service/cart/cache.py", "raw = client.get(", 10)
    steps = background(start, 20)
    t = 3.0
    while t < 18:
        base = start + timedelta(seconds=t)
        tr, g, c = _tid(), _sid(), _sid()
        stack = ("Traceback (most recent call last):\n"
                 f'  File "/app/cart/cache.py", line {l_get}, in load_cart\n'
                 '    raw = client.get(f"cart:{user_id}")\n'
                 '  File "/usr/local/lib/python3.12/site-packages/redis/connection.py", line 353, in connect\n'
                 "    raise ConnectionError(self._error_message(e))\n"
                 "redis.exceptions.ConnectionError: Error 111 connecting to redis-cart:6379. Connection refused.")
        steps += [
            (t, "log", jlog(base, "ERROR", "cart-service",
                            "redis.exceptions.ConnectionError: Error 111 connecting to redis-cart:6379. "
                            "Connection refused.", tr, c, g, logger="cart.cache", stack_trace=stack,
                            peer_service="redis")),
            (t, "log", gw_line(base + timedelta(milliseconds=6), "ERROR",
                               "GET /api/cart 503 upstream cart-service failed", tr, g)),
        ]
        t += random.uniform(0.4, 0.9)
    return steps


def brute_force_login(start: datetime) -> list:
    ip = "203.0.113.45"
    steps = background(start, 18, every=0.9)
    names = ["admin", "root", "administrator", "test", "admin", "support", "admin", "guest", "admin", "oracle",
             "admin", "devops", "admin", "admin"]
    t = 2.0
    for u in names:
        steps.append((t, "log", jlog(start + timedelta(seconds=t), "WARN", "auth-service",
                                     f"Login failed for user {u} from {ip}: invalid password", logger="auth.login",
                                     event="auth_failure", username=u, client_ip=ip,
                                     user_agent="python-requests/2.31")))
        t += random.uniform(0.4, 0.9)
    steps.append((t + 0.5, "log", jlog(start + timedelta(seconds=t + 0.5), "INFO", "auth-service",
                                       f"Login succeeded for user admin from {ip}", logger="auth.login",
                                       event="auth_success", username="admin", client_ip=ip,
                                       user_agent="python-requests/2.31")))
    return steps


GENERATORS = {
    "db_pool_exhaustion": db_pool_exhaustion,
    "inventory_null_pointer": inventory_null_pointer,
    "cache_outage": cache_outage,
    "brute_force_login": brute_force_login,
}


def build(name: str, start: datetime) -> list:
    return sorted(GENERATORS[name](start), key=lambda s: s[0])

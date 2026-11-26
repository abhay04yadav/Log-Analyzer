"""Event bus (S1 -> worker). Redis Streams with consumer groups; in-memory queue as fallback.

The ingestion API only validates and publishes; processing happens in the worker, so bursts of
logs never block producers and the worker can be scaled out (more consumers in the same group).
"""

import json
import logging
import queue
import threading
from abc import ABC, abstractmethod

log = logging.getLogger("sla.bus")

RAW_STREAM = "sla:logs:raw"
GROUP = "sla-workers"


class EventBus(ABC):
    kind = "abstract"

    @abstractmethod
    def publish(self, stream: str, payload: dict) -> str: ...

    @abstractmethod
    def read(self, stream: str, consumer: str, count: int = 50,
             block_ms: int = 1000) -> list[tuple[str, dict]]: ...

    def ack(self, stream: str, ids: list[str]) -> None:  # noqa: B027
        pass

    def backlog(self, stream: str) -> int:
        return 0


class MemoryBus(EventBus):
    kind = "memory"

    def __init__(self):
        self.queues: dict[str, queue.Queue] = {}
        self.lock = threading.Lock()
        self.seq = 0

    def _q(self, stream):
        with self.lock:
            return self.queues.setdefault(stream, queue.Queue())

    def publish(self, stream, payload):
        with self.lock:
            self.seq += 1
            msg_id = f"{self.seq}-0"
        self._q(stream).put((msg_id, payload))
        return msg_id

    def read(self, stream, consumer, count=50, block_ms=1000):
        q, out = self._q(stream), []
        try:
            out.append(q.get(timeout=block_ms / 1000))
            while len(out) < count:
                out.append(q.get_nowait())
        except queue.Empty:
            pass
        return out

    def backlog(self, stream):
        return self._q(stream).qsize()


class RedisStreamsBus(EventBus):
    kind = "redis-streams"

    def __init__(self, url: str):
        import redis

        self.r = redis.Redis.from_url(
            url, decode_responses=True, socket_timeout=10)
        self.r.ping()
        self._groups: set[str] = set()

    def _ensure_group(self, stream):
        if stream in self._groups:
            return
        try:
            self.r.xgroup_create(stream, GROUP, id="0", mkstream=True)
        except Exception as e:  # BUSYGROUP = already exists
            if "BUSYGROUP" not in str(e):
                raise
        self._groups.add(stream)

    def publish(self, stream, payload):
        return self.r.xadd(stream, {"data": json.dumps(payload, default=str)}, maxlen=100_000, approximate=True)

    def read(self, stream, consumer, count=50, block_ms=1000):
        self._ensure_group(stream)
        resp = self.r.xreadgroup(
            GROUP, consumer, {stream: ">"}, count=count, block=block_ms)
        return [(mid, json.loads(fields["data"])) for _, msgs in (resp or []) for mid, fields in msgs]

    def ack(self, stream, ids):
        if ids:
            self.r.xack(stream, GROUP, *ids)

    def backlog(self, stream):
        try:
            self._ensure_group(stream)
            info = self.r.xinfo_groups(stream)
            return sum(int(g.get("lag") or 0) for g in info if g["name"] == GROUP)
        except Exception:
            return 0


_bus: EventBus | None = None


def get_bus() -> EventBus:
    global _bus
    if _bus is None:
        from app.core.config import get_settings

        url = get_settings().redis_url
        if url:
            try:
                _bus = RedisStreamsBus(url)
                log.info("event bus: Redis Streams at %s", url)
            except Exception as e:
                log.warning(
                    "Redis unavailable (%s) -- falling back to in-memory queue", e)
        if _bus is None:
            _bus = MemoryBus()
            log.info("event bus: in-memory queue (lite mode)")
    return _bus

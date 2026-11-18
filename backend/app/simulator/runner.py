"""Plays simulator scenarios in real time through the normal ingestion path (event bus)."""
import logging
import random
import threading
import time

from app.bus import RAW_STREAM, get_bus
from app.db import SessionLocal, utcnow
from app.simulator import scenarios

log = logging.getLogger("sla.simulator")


class SimulatorRunner:
    def __init__(self):
        self.lock = threading.Lock()
        self.running: dict[str, dict] = {}
        self.traffic_stop: threading.Event | None = None

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _publish(project_id: int, items: list):
        if items:
            get_bus().publish(RAW_STREAM, {"project_id": project_id, "events": items})

    @staticmethod
    def _deploy(project_id: int, d: dict):
        from app.api.ingest import store_deployment  # local import: avoids an import cycle

        with SessionLocal() as db:
            store_deployment(db, project_id, d)
            db.commit()

    # ------------------------------------------------------------------ scenarios
    def run(self, project_id: int, name: str) -> dict:
        if name not in scenarios.GENERATORS:
            raise KeyError(name)
        with self.lock:
            if name in self.running:
                return self.running[name]
            info = {"scenario": name, "started_at": utcnow().isoformat() + "Z", "events": 0}
            self.running[name] = info
        threading.Thread(target=self._play, args=(project_id, name, info), daemon=True).start()
        return info

    def _play(self, project_id: int, name: str, info: dict):
        try:
            start = utcnow()
            steps = scenarios.build(name, start)
            t0 = time.monotonic()
            i = 0
            while i < len(steps):
                due = steps[i][0]
                wait = due - (time.monotonic() - t0)
                if wait > 0:
                    time.sleep(min(wait, 0.5))
                    continue
                batch = []
                while i < len(steps) and steps[i][0] <= (time.monotonic() - t0) + 0.25:
                    _, kind, item = steps[i]
                    if kind == "deploy":
                        self._deploy(project_id, item)
                    else:
                        batch.append(item)
                    i += 1
                self._publish(project_id, batch)
                info["events"] += len(batch)
        except Exception:
            log.exception("scenario %s failed", name)
        finally:
            with self.lock:
                self.running.pop(name, None)

    # ------------------------------------------------------------------ background traffic
    def start_traffic(self, project_id: int):
        with self.lock:
            if self.traffic_stop:
                return
            self.traffic_stop = threading.Event()
        threading.Thread(target=self._traffic, args=(project_id, self.traffic_stop), daemon=True).start()

    def stop_traffic(self):
        with self.lock:
            if self.traffic_stop:
                self.traffic_stop.set()
                self.traffic_stop = None

    def _traffic(self, project_id: int, stop: threading.Event):
        last_noise = time.monotonic()
        while not stop.wait(1.0):
            now = utcnow()
            items = [item for _, _, item in scenarios.background(now, 1.0, every=0.35)]
            if time.monotonic() - last_noise > 45 and random.random() < 0.3:   # rare, harmless error
                last_noise = time.monotonic()
                items.append(scenarios.logfmt(now, "error", "checkout-service",
                                              "CouponValidationError: coupon code expired",
                                              error_type="CouponValidationError"))
            self._publish(project_id, items)

    def status(self) -> dict:
        return {"running": list(self.running.values()), "traffic": self.traffic_stop is not None}


runner = SimulatorRunner()

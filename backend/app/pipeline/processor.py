"""Pipeline orchestration and the background worker.

  API (S1) --publish--> event bus --consume--> worker:
      S2 normalise -> S3 fingerprint -> detect -> S4 correlate -> S5 traceback + S6 rank
      (S7 recommendation runs once the incident has been quiet for a few seconds)
"""
import logging
import os
import socket
import threading
import time
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.bus import RAW_STREAM, get_bus
from app.core.config import get_settings
from app.db import SessionLocal, utcnow
from app.models import ErrorSignature, Incident, KnownError, LogEvent
from app.pipeline.correlate import correlate
from app.pipeline.detect import detect, match_known
from app.pipeline.fingerprint import fingerprint, template
from app.pipeline.normalize import normalise
from app.pipeline.rank import analyse
from app.pipeline.recommend import recommend

log = logging.getLogger("sla.worker")
settings = get_settings()
stats = {"processed_events": 0, "processed_batches": 0, "last_batch_at": None, "errors": 0}


def process_batch(db: Session, project_id: int, items: list, default_service: str | None = None,
                  ts_offset_seconds: float = 0.0) -> set[int]:
    known = list(db.scalars(select(KnownError)))
    events: list[LogEvent] = []
    for item in items:
        try:
            n = normalise(item, default_service, settings.max_message_chars)
        except Exception as e:  # one malformed line must never stop the batch
            log.warning("could not normalise item: %s", e)
            n = normalise(str(item)[:2000], default_service, settings.max_message_chars)
        if ts_offset_seconds:                      # replayed log file: shift to "now"
            n["ts"] = n["ts"] + timedelta(seconds=ts_offset_seconds)
        ev = LogEvent(project_id=project_id, received_at=utcnow(), **n)
        if ev.is_error:
            ev.fingerprint = fingerprint(ev.service, ev.error_type, ev.message, ev.stack)
        events.append(ev)
    db.add_all(events)
    db.flush()

    # S3: keep a catalogue of distinct failures
    for ev in events:
        if not ev.fingerprint:
            continue
        sig = db.get(ErrorSignature, ev.fingerprint)
        if sig is None:
            k = match_known(known, ev.error_type, ev.message)
            sig = ErrorSignature(fingerprint=ev.fingerprint, project_id=project_id, service=ev.service,
                                 error_type=ev.error_type, template=template(ev.message), first_seen=ev.ts,
                                 last_seen=ev.ts, count=0, known_error_id=k.id if k else None,
                                 confirmed_root_cause=0)
            db.add(sig)
            db.flush()
        sig.count += 1
        sig.last_seen = max(sig.last_seen, ev.ts)

    detections = detect(db, project_id, events, known)
    touched = correlate(db, project_id, events, detections)
    for inc_id in touched:
        inc = db.get(Incident, inc_id)
        analyse(db, inc)
        inc.updated_at = utcnow()
        top = inc.candidates[0] if inc.candidates else None
        latest = inc.recommendations[0] if inc.recommendations else None
        if top and (latest is None or latest.candidate_fingerprint != top.fingerprint):
            inc.needs_recommendation = True
    db.commit()
    return touched


def run_pending_recommendations(db: Session) -> int:
    quiet = utcnow() - timedelta(seconds=settings.recommend_debounce_seconds)
    pending = db.scalars(select(Incident).where(Incident.needs_recommendation.is_(True),
                                                Incident.updated_at <= quiet)).all()
    for inc in pending:
        try:
            recommend(db, inc)
            db.commit()
        except Exception:
            log.exception("recommendation failed for incident %s", inc.id)
            db.rollback()
            inc.needs_recommendation = False
            db.commit()
    return len(pending)


class Worker:
    def __init__(self, name: str | None = None, recommender: bool = True):
        self.name = name or f"worker-{socket.gethostname()}-{os.getpid()}"   # unique consumer in the group
        self.recommender = recommender
        self.stop = threading.Event()
        self.thread: threading.Thread | None = None
        self.rec_thread: threading.Thread | None = None

    def start(self):
        self.thread = threading.Thread(target=self.run, name=self.name, daemon=True)
        self.thread.start()
        # recommendations (possibly slow LLM calls) run separately so ingestion never waits for the AI;
        # only one process (the API) runs them, extra workers only process logs
        if self.recommender:
            self.rec_thread = threading.Thread(target=self.run_recommendations, name=f"{self.name}-s7", daemon=True)
            self.rec_thread.start()

    def run_recommendations(self):
        while not self.stop.wait(1.0):
            try:
                with SessionLocal() as db:
                    run_pending_recommendations(db)
            except Exception:
                log.exception("recommendation loop error")

    def run(self):
        bus = get_bus()
        log.info("worker %s consuming %s via %s", self.name, RAW_STREAM, bus.kind)
        while not self.stop.is_set():
            try:
                msgs = bus.read(RAW_STREAM, self.name, count=20, block_ms=1000)
                if msgs:
                    with SessionLocal() as db:
                        for msg_id, payload in msgs:
                            try:
                                process_batch(db, payload["project_id"], payload["events"],
                                              payload.get("default_service"),
                                              payload.get("ts_offset_seconds") or 0.0)
                                stats["processed_events"] += len(payload["events"])
                                stats["processed_batches"] += 1
                                stats["last_batch_at"] = utcnow().isoformat() + "Z"
                            except Exception:
                                stats["errors"] += 1
                                log.exception("failed to process message %s", msg_id)
                                db.rollback()
                    bus.ack(RAW_STREAM, [m for m, _ in msgs])
            except Exception:
                log.exception("worker loop error")
                time.sleep(1)

    def shutdown(self):
        self.stop.set()
        for t in (self.thread, self.rec_thread):
            if t:
                t.join(timeout=5)


if __name__ == "__main__":  # standalone worker process:  python -m app.pipeline.processor
    logging.basicConfig(level=logging.INFO)
    from app.db import init_db
    from app.seed import seed

    init_db()
    seed()
    w = Worker(recommender=False)
    w.start()
    w.thread.join()

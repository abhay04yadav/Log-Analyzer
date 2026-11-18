"""S4 - Correlate events into incidents.

1. A detection opens an incident, or joins an open incident of the same kind that was active within
   INCIDENT_GAP *and* is related to it (same fingerprint, or shares a trace / request id).
2. Error events close in time to an open incident are attached when they are related to it
   (same fingerprint, or same trace / request).
3. Trace expansion: every event sharing a trace / request id with an attached event is attached too,
   so the incident holds the full request path, including INFO / WARN context.
Unrelated failures at the same time therefore become separate incidents, even when they share a
service such as the API gateway.
"""
from datetime import timedelta

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db import utcnow
from app.models import Incident, LogEvent
from app.pipeline.detect import Detection, source_ip

settings = get_settings()
LOOKBACK = timedelta(seconds=120)
SEV_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def _incident_keys(db: Session, inc: Incident) -> tuple[set, set, set]:
    """Fingerprints, trace ids and request ids already in the incident."""
    rows = db.execute(select(LogEvent.fingerprint, LogEvent.trace_id, LogEvent.request_id)
                      .where(LogEvent.incident_id == inc.id)).all()
    return ({f for f, _, _ in rows if f}, {t for _, t, _ in rows if t}, {r for _, _, r in rows if r})


def _related(ev: LogEvent, keys) -> bool:
    """Same failure (fingerprint) or same request path (trace / request id).

    Sharing only a service name is not enough: edge services such as the API gateway take part in
    almost every failure, and would otherwise merge unrelated incidents."""
    fps, traces, reqs = keys
    return (ev.fingerprint is not None and ev.fingerprint in fps) or \
        (ev.trace_id is not None and ev.trace_id in traces) or \
        (ev.request_id is not None and ev.request_id in reqs)


def _find_incident(db, project_id, d: Detection, evs: list[LogEvent], at) -> Incident | None:
    gap = timedelta(seconds=settings.incident_gap_seconds)
    q = select(Incident).where(Incident.project_id == project_id, Incident.status == "open",
                               Incident.category == d.category, Incident.window_end >= at - gap)
    if d.group_key:
        return db.scalars(q.where(Incident.group_key == d.group_key).order_by(Incident.id.desc())).first()
    for inc in db.scalars(q.order_by(Incident.id.desc())).all():
        keys = _incident_keys(db, inc)
        if any(_related(e, keys) for e in evs):
            return inc
    return None


def _expand(db: Session, inc: Incident, project_id: int, candidates: list[LogEvent]) -> None:
    """Attach related unassigned errors, then pull in everything on the same traces / requests."""
    for _ in range(3):                                  # a few rounds: traces bring in new services
        keys = _incident_keys(db, inc)
        ids = [e.id for e in candidates if e.incident_id is None and _related(e, keys)]
        if ids:
            db.execute(update(LogEvent).where(LogEvent.id.in_(ids)).values(incident_id=inc.id))
            for e in candidates:
                if e.id in ids:
                    e.incident_id = inc.id
        _, traces, reqs = _incident_keys(db, inc)
        conds = ([LogEvent.trace_id.in_(traces)] if traces else []) + \
                ([LogEvent.request_id.in_(reqs)] if reqs else [])
        if conds:
            res = db.execute(update(LogEvent).where(
                LogEvent.project_id == project_id, LogEvent.incident_id.is_(None), or_(*conds)
            ).values(incident_id=inc.id).execution_options(synchronize_session=False))
            if res.rowcount:
                db.flush()
                db.expire_all()
        if not ids:
            break


def _attach_warnings(db: Session, inc: Incident, project_id: int) -> None:
    """Warnings without trace context (e.g. 'connection pool usage high') from services that are failing
    in this incident, logged shortly before or during it, are often the best early evidence."""
    rows = db.execute(select(LogEvent.service, LogEvent.ts).where(
        LogEvent.incident_id == inc.id, LogEvent.is_error.is_(True))).all()
    if not rows:
        return
    services = {s for s, _ in rows}
    lo, hi = min(t for _, t in rows) - LOOKBACK, max(t for _, t in rows)
    db.execute(update(LogEvent).where(
        LogEvent.project_id == project_id, LogEvent.incident_id.is_(None), LogEvent.level == "WARN",
        LogEvent.trace_id.is_(None), LogEvent.service.in_(services), LogEvent.ts >= lo, LogEvent.ts <= hi,
    ).values(incident_id=inc.id).execution_options(synchronize_session=False))


def correlate(db: Session, project_id: int, batch: list[LogEvent], detections: list[Detection]) -> set[int]:
    touched: set[int] = set()
    by_id = {e.id: e for e in batch}

    for d in detections:
        evs = [by_id[i] for i in d.event_ids if i in by_id]
        if not evs:
            evs = list(db.scalars(select(LogEvent).where(LogEvent.id.in_(d.event_ids))))
        at = min(e.ts for e in evs)
        inc = _find_incident(db, project_id, d, evs, at)
        if inc is None:
            inc = Incident(project_id=project_id, title=d.label, category=d.category, severity=d.severity,
                           detection=[], group_key=d.group_key, window_start=at, window_end=at,
                           services=sorted({e.service for e in evs}), created_at=utcnow())
            db.add(inc)
            db.flush()
        # one entry per (detector, failure); a growing spike updates its label instead of adding a new one
        entry = {"kind": d.kind, "label": d.label, "fingerprint": d.fingerprint}
        rest = [x for x in inc.detection if (x["kind"], x.get("fingerprint")) != (d.kind, d.fingerprint)]
        if len(rest) < 20:
            inc.detection = rest + [entry]
        if SEV_ORDER.get(d.severity, 1) > SEV_ORDER.get(inc.severity, 1):
            inc.severity = d.severity
        db.execute(update(LogEvent).where(LogEvent.id.in_(d.event_ids), LogEvent.incident_id.is_(None))
                   .values(incident_id=inc.id).execution_options(synchronize_session=False))
        db.flush()
        db.expire_all()
        touched.add(inc.id)

    if not batch:
        return touched
    # attach related errors from this batch and recent unassigned errors to active incidents
    lo, hi = min(e.ts for e in batch), max(e.ts for e in batch)
    gap = timedelta(seconds=settings.incident_gap_seconds)
    active = db.scalars(select(Incident).where(
        Incident.project_id == project_id, Incident.status == "open", Incident.category == "error",
        Incident.window_end >= lo - gap)).all()
    if active:
        pool = list(db.scalars(select(LogEvent).where(
            LogEvent.project_id == project_id, LogEvent.incident_id.is_(None), LogEvent.is_error.is_(True),
            LogEvent.ts >= lo - LOOKBACK, LogEvent.ts <= hi)))
        for inc in active:
            _expand(db, inc, project_id, pool)
            _attach_warnings(db, inc, project_id)
    # security incidents: later events from the same source IP (e.g. a successful login) join the incident
    sec = db.scalars(select(Incident).where(
        Incident.project_id == project_id, Incident.status == "open", Incident.category == "security",
        Incident.window_end >= lo - gap)).all()
    if sec:
        by_ip = {i.group_key: i for i in sec}
        for e in batch:
            if e.incident_id is None and (ip := source_ip(e)) in by_ip:
                e.incident_id = by_ip[ip].id
    # any incident that received events from this batch must be re-analysed
    ids = {e.id for e in batch}
    for inc_id in db.scalars(select(LogEvent.incident_id).where(LogEvent.id.in_(ids),
                                                                LogEvent.incident_id.is_not(None)).distinct()):
        touched.add(inc_id)
    db.flush()
    return touched

"""Log search, live stream and overview statistics (dashboard, bearer-token protected)."""
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.api.serializers import deployment_out, event_out, iso
from app.core.security import current_user
from app.db import IS_POSTGRES, get_db, utcnow
from app.models import Deployment, ErrorSignature, Incident, LogEvent

router = APIRouter(prefix="/api/v1", tags=["logs"], dependencies=[Depends(current_user)])


@router.get("/events")
def search_events(q: str | None = Query(None, max_length=200), service: str | None = None,
                  level: str | None = None, trace_id: str | None = None, incident_id: int | None = None,
                  errors_only: bool = False, after_id: int | None = None, limit: int = Query(100, le=500),
                  db: Session = Depends(get_db)):
    stmt = select(LogEvent)
    if q:
        if IS_POSTGRES:   # PostgreSQL full-text search (GIN index) + substring fallback
            stmt = stmt.where(or_(func.to_tsvector("simple", LogEvent.message).op("@@")(
                func.plainto_tsquery("simple", q)), LogEvent.message.ilike(f"%{q}%")))
        else:
            stmt = stmt.where(or_(LogEvent.message.ilike(f"%{q}%"), LogEvent.error_type.ilike(f"%{q}%")))
    if service:
        stmt = stmt.where(LogEvent.service == service)
    if level:
        stmt = stmt.where(LogEvent.level.in_(level.upper().split(",")))
    if trace_id:
        stmt = stmt.where(LogEvent.trace_id == trace_id)
    if incident_id:
        stmt = stmt.where(LogEvent.incident_id == incident_id)
    if errors_only:
        stmt = stmt.where(LogEvent.is_error.is_(True))
    if after_id:
        stmt = stmt.where(LogEvent.id > after_id)
    rows = db.scalars(stmt.order_by(LogEvent.id.desc()).limit(limit)).all()
    return {"items": [event_out(e) for e in rows]}


@router.get("/events/{event_id}")
def get_event(event_id: int, db: Session = Depends(get_db)):
    e = db.get(LogEvent, event_id)
    if not e:
        raise HTTPException(404, "event not found")
    return event_out(e, full=True)


@router.get("/services")
def services(db: Session = Depends(get_db)):
    since = utcnow() - timedelta(minutes=15)
    rows = db.execute(select(LogEvent.service, func.count(), func.sum(case((LogEvent.is_error, 1), else_=0)),
                             func.max(LogEvent.ts))
                      .where(LogEvent.ts >= since).group_by(LogEvent.service)).all()
    return {"items": [{"service": s, "events": n, "errors": int(e or 0), "last_seen": iso(t)}
                      for s, n, e, t in sorted(rows)]}


@router.get("/stats/overview")
def overview(db: Session = Depends(get_db)):
    now = utcnow()
    since = now - timedelta(minutes=15)
    total, errors = db.execute(select(func.count(), func.sum(case((LogEvent.is_error, 1), else_=0)))
                               .where(LogEvent.ts >= since)).one()
    open_inc = db.scalar(select(func.count()).where(Incident.status == "open"))
    resolved = db.scalar(select(func.count()).where(Incident.status == "resolved"))
    sec = db.scalar(select(func.count()).where(Incident.status == "open", Incident.category == "security"))
    sigs = db.scalar(select(func.count()).select_from(ErrorSignature))
    svc = db.scalar(select(func.count(func.distinct(LogEvent.service))).where(LogEvent.ts >= since))
    all_events = db.scalar(select(func.count()).select_from(LogEvent))
    return {"events_15m": total or 0, "errors_15m": int(errors or 0), "open_incidents": open_inc,
            "resolved_incidents": resolved, "security_incidents": sec, "fingerprints": sigs,
            "services": svc, "total_events": all_events}


@router.get("/stats/timeseries")
def timeseries(minutes: int = Query(15, ge=1, le=180), db: Session = Depends(get_db)):
    """Events per bucket split by level (bucketed in Python to stay database-independent)."""
    now = utcnow()
    since = now - timedelta(minutes=minutes)
    bucket = 10 if minutes <= 15 else 60
    rows = db.execute(select(LogEvent.ts, LogEvent.level).where(LogEvent.ts >= since)).all()
    n = int(minutes * 60 / bucket)
    series = [{"t": iso(since + timedelta(seconds=i * bucket)), "INFO": 0, "WARN": 0, "ERROR": 0} for i in range(n)]
    for ts, level in rows:
        i = int((ts - since).total_seconds() // bucket)
        if 0 <= i < n:
            key = "ERROR" if level in ("ERROR", "CRITICAL") else "WARN" if level == "WARN" else "INFO"
            series[i][key] += 1
    return {"bucket_seconds": bucket, "items": series}


@router.get("/deployments")
def deployments(limit: int = Query(20, le=100), db: Session = Depends(get_db)):
    rows = db.scalars(select(Deployment).order_by(Deployment.ts.desc()).limit(limit)).all()
    return {"items": [deployment_out(d) for d in rows]}

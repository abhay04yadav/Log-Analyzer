"""Incident investigation API: list, detail (timeline, graph, candidates, code, recommendation), feedback."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.serializers import (candidate_out, deployment_out, event_out, feedback_out, incident_summary,
                                 recommendation_out)
from app.core.config import get_settings
from app.core.security import current_user
from app.db import get_db
from app.models import Candidate, Deployment, Incident, KnownError, LogEvent
from app.pipeline.feedback import apply_feedback
from app.pipeline.rank import SIGNAL_NAMES, get_weights
from app.pipeline.recommend import recommend

router = APIRouter(prefix="/api/v1/incidents", tags=["incidents"])


def _get(db: Session, incident_id: int) -> Incident:
    inc = db.get(Incident, incident_id)
    if not inc:
        raise HTTPException(404, "incident not found")
    return inc


@router.get("")
def list_incidents(status: str | None = None, category: str | None = None, limit: int = Query(50, le=200),
                   db: Session = Depends(get_db), _: str = Depends(current_user)):
    stmt = select(Incident)
    if status:
        stmt = stmt.where(Incident.status == status)
    if category:
        stmt = stmt.where(Incident.category == category)
    rows = db.scalars(stmt.order_by(Incident.id.desc()).limit(limit)).all()
    return {"items": [incident_summary(i) for i in rows]}


@router.get("/{incident_id}")
def incident_detail(incident_id: int, db: Session = Depends(get_db), _: str = Depends(current_user)):
    inc = _get(db, incident_id)
    events = db.scalars(select(LogEvent).where(LogEvent.incident_id == inc.id).order_by(LogEvent.ts, LogEvent.id)
                        .limit(400)).all()
    dep_ids = {c.deployment_id for c in inc.candidates if c.deployment_id}
    deps = db.scalars(select(Deployment).where(Deployment.id.in_(dep_ids))).all() if dep_ids else []
    known_ids = {c.known_error_id for c in inc.candidates if c.known_error_id}
    known = db.scalars(select(KnownError).where(KnownError.id.in_(known_ids))).all() if known_ids else []
    weights = get_weights(db)
    return {
        **incident_summary(inc),
        "detection": inc.detection,
        "graph": inc.graph or {"nodes": [], "edges": []},
        "candidates": [candidate_out(c) for c in inc.candidates],
        "weights": weights,
        "signal_names": SIGNAL_NAMES,
        "timeline": [event_out(e) for e in events],
        "deployments": [deployment_out(d) for d in deps],
        "known_errors": [{"id": k.id, "name": k.name, "category": k.category} for k in known],
        "recommendations": [recommendation_out(r) for r in inc.recommendations],
        "recommendation_pending": inc.needs_recommendation,
        "feedback": [feedback_out(f) for f in inc.feedback],
        "ai": {"provider": get_settings().llm_provider, "enabled": get_settings().llm_enabled,
               "model": get_settings().gemini_model},
    }


@router.post("/{incident_id}/recommend")
def regenerate(incident_id: int, db: Session = Depends(get_db), _: str = Depends(current_user)):
    """Ask the AI provider for a (new) recommendation for the current top candidate."""
    inc = _get(db, incident_id)
    rec = recommend(db, inc, force_llm=True)
    if rec is None:
        raise HTTPException(409, "incident has no root-cause candidates yet")
    db.commit()
    return recommendation_out(rec)


class FeedbackRequest(BaseModel):
    verdict: Literal["confirmed", "rejected", "resolved"]
    candidate_id: int | None = None
    note: str | None = Field(None, max_length=2000)


@router.post("/{incident_id}/feedback")
def feedback(incident_id: int, body: FeedbackRequest, db: Session = Depends(get_db),
             user: str = Depends(current_user)):
    inc = _get(db, incident_id)
    cand = None
    if body.candidate_id is not None:
        cand = db.get(Candidate, body.candidate_id)
        if not cand or cand.incident_id != inc.id:
            raise HTTPException(404, "candidate not found in this incident")
    elif body.verdict != "resolved":
        raise HTTPException(422, "candidate_id is required for confirmed / rejected")
    fb = apply_feedback(db, inc, cand, body.verdict, body.note, user)
    db.commit()
    return feedback_out(fb)

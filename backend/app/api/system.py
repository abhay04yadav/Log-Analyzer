"""System status, ranking weights, playbook, failure drills (simulator) and data reset."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from app.bus import RAW_STREAM, get_bus
from app.core.config import get_settings
from app.core.security import current_user
from app.db import IS_POSTGRES, IS_SQLITE, engine, get_db
from app.models import (Candidate, Deployment, ErrorSignature, Feedback, Incident, KnownError, LogEvent, Project,
                        Recommendation, Setting)
from app.pipeline.processor import stats as worker_stats
from app.pipeline.rank import DEFAULT_WEIGHTS, SIGNAL_NAMES
from app.simulator import scenarios
from app.simulator.runner import runner

router = APIRouter(prefix="/api/v1", tags=["system"], dependencies=[Depends(current_user)])
settings = get_settings()


@router.get("/system/status")
def status():
    bus = get_bus()
    return {"database": "postgresql" if IS_POSTGRES else "sqlite" if IS_SQLITE else engine.dialect.name,
            "event_bus": bus.kind, "bus_backlog": bus.backlog(RAW_STREAM), "worker": worker_stats,
            "ai": {"provider": settings.llm_provider, "enabled": settings.llm_enabled, "model": settings.gemini_model},
            "simulator": runner.status()}


@router.get("/settings/weights")
def weights(db: Session = Depends(get_db)):
    s = db.get(Setting, "weights")
    value = s.value if s else {"current": DEFAULT_WEIGHTS, "default": DEFAULT_WEIGHTS, "history": []}
    return {**value, "names": SIGNAL_NAMES}


@router.post("/settings/weights/reset")
def reset_weights(db: Session = Depends(get_db)):
    s = db.get(Setting, "weights")
    value = {"current": DEFAULT_WEIGHTS, "default": DEFAULT_WEIGHTS, "history": []}
    if s:
        s.value = value
    else:
        db.add(Setting(key="weights", value=value))
    db.commit()
    return value


@router.get("/playbook")
def playbook(db: Session = Depends(get_db)):
    rows = db.scalars(select(KnownError).order_by(KnownError.id)).all()
    return {"items": [{"id": k.id, "name": k.name, "category": k.category, "severity": k.severity,
                       "pattern": k.pattern, "root_cause": k.root_cause, "fix_steps": k.fix_steps} for k in rows]}


@router.get("/simulator/scenarios")
def list_scenarios():
    return {"items": [{"id": k, **v} for k, v in scenarios.SCENARIOS.items()], "status": runner.status()}


class RunRequest(BaseModel):
    scenario: str


def _project_id(db: Session) -> int:
    pid = db.scalar(select(Project.id).order_by(Project.id).limit(1))
    if pid is None:
        raise HTTPException(500, "no project configured")
    return pid


@router.post("/simulator/run")
def run_scenario(body: RunRequest, db: Session = Depends(get_db)):
    if body.scenario not in scenarios.GENERATORS:
        raise HTTPException(404, "unknown scenario")
    return runner.run(_project_id(db), body.scenario)


@router.post("/simulator/traffic/{action}")
def traffic(action: str, db: Session = Depends(get_db)):
    if action == "start":
        runner.start_traffic(_project_id(db))
    elif action == "stop":
        runner.stop_traffic()
    else:
        raise HTTPException(404, "use start or stop")
    return runner.status()


@router.post("/admin/reset")
def reset(db: Session = Depends(get_db)):
    """Clear logs, incidents and learned weights (keeps project + playbook). Useful between presentations / test runs."""
    for model in (Feedback, Recommendation, Candidate):
        db.execute(delete(model))
    db.execute(delete(LogEvent))
    db.execute(delete(Incident))
    db.execute(delete(ErrorSignature))
    db.execute(delete(Deployment))
    db.execute(delete(Setting).where(Setting.key == "weights"))
    db.add(Setting(key="weights", value={"current": DEFAULT_WEIGHTS, "default": DEFAULT_WEIGHTS, "history": []}))
    db.commit()
    if IS_SQLITE:
        with engine.connect() as conn:
            conn.execute(text("PRAGMA wal_checkpoint(TRUNCATE)"))
    return {"status": "cleared"}

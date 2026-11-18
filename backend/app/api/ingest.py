"""S1 - Ingestion API (authenticated with a per-project API key).

The endpoint only validates and publishes to the event bus; it returns 202 immediately.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.bus import RAW_STREAM, get_bus
from app.core.config import get_settings
from app.core.security import current_user, project_from_api_key
from app.db import get_db, utcnow
from app.models import Deployment, Project
from app.pipeline.normalize import _parse_ts, normalise, split_entries

router = APIRouter(prefix="/api/v1", tags=["ingestion"])
settings = get_settings()


class IngestRequest(BaseModel):
    events: list[dict | str] = Field(..., min_length=1, description="JSON log objects or raw log lines")
    service: str | None = Field(None, max_length=120, description="default service name for raw lines")

    @field_validator("events")
    @classmethod
    def _limit(cls, v):
        if len(v) > settings.max_batch_events:
            raise ValueError(f"at most {settings.max_batch_events} events per request")
        for item in v:
            size = len(item) if isinstance(item, str) else len(str(item))
            if size > settings.max_message_chars * 4:
                raise ValueError("event too large")
        return v


class DeploymentRequest(BaseModel):
    service: str = Field(..., max_length=120)
    version: str = Field(..., max_length=60)
    commit: str | None = Field(None, max_length=60)
    author: str | None = Field(None, max_length=120)
    description: str | None = Field(None, max_length=2000)
    changed_files: list[str] = Field(default_factory=list, max_length=500)
    ts: datetime | str | None = None


@router.post("/ingest", status_code=202)
def ingest(body: IngestRequest, project: Project = Depends(project_from_api_key)):
    msg_id = get_bus().publish(RAW_STREAM, {"project_id": project.id, "events": body.events,
                                            "default_service": body.service})
    return {"accepted": len(body.events), "message_id": msg_id}


MAX_FILE_CHARS = 5_000_000
CHUNK = 500


class TextIngestRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=MAX_FILE_CHARS, description="log file contents")
    service: str | None = Field(None, max_length=120, description="service name for lines that carry none")
    filename: str | None = Field(None, max_length=255)
    replay: bool = Field(False, description="shift timestamps so the file ends now (replay as live traffic)")


def publish_text(project_id: int, body: TextIngestRequest) -> dict:
    """Split a log file into entries (multi-line stack traces stay together) and publish in chunks."""
    entries = split_entries(body.content, settings.max_message_chars)
    if not entries:
        raise HTTPException(422, "no log entries found")
    offset = 0.0
    parsed = [normalise(e, body.service, 2000)["ts"] for e in entries]
    if body.replay and parsed:
        offset = (utcnow() - max(parsed)).total_seconds()
    bus = get_bus()
    for i in range(0, len(entries), CHUNK):
        bus.publish(RAW_STREAM, {"project_id": project_id, "events": entries[i:i + CHUNK],
                                 "default_service": body.service, "ts_offset_seconds": offset})
    return {"accepted": len(entries), "chunks": (len(entries) + CHUNK - 1) // CHUNK,
            "first_ts": min(parsed).isoformat() + "Z", "last_ts": max(parsed).isoformat() + "Z",
            "replay_offset_seconds": round(offset, 1), "filename": body.filename}


@router.post("/ingest/text", status_code=202)
def ingest_text(body: TextIngestRequest, project: Project = Depends(project_from_api_key)):
    """Ingest a whole log file (plain text) with the project API key - e.g. from a log shipper or CI job."""
    return publish_text(project.id, body)


@router.post("/upload", status_code=202)
def upload(body: TextIngestRequest, _: str = Depends(current_user), db: Session = Depends(get_db)):
    """Log file upload from the dashboard (signed-in user, default project)."""
    pid = db.scalar(select(Project.id).order_by(Project.id).limit(1))
    return publish_text(pid, body)


def store_deployment(db: Session, project_id: int, d: dict) -> Deployment:
    from app.db import utcnow

    dep = Deployment(project_id=project_id, service=d["service"], version=d["version"], commit=d.get("commit"),
                     author=d.get("author"), description=d.get("description"),
                     changed_files=list(d.get("changed_files") or []),
                     ts=_parse_ts(d.get("ts")) or utcnow())
    db.add(dep)
    return dep


@router.post("/deployments", status_code=201)
def create_deployment(body: DeploymentRequest, project: Project = Depends(project_from_api_key),
                      db: Session = Depends(get_db)):
    dep = store_deployment(db, project.id, body.model_dump())
    db.commit()
    if not dep.ts:
        raise HTTPException(400, "invalid timestamp")
    return {"id": dep.id}


@router.get("/project")
def project_info(_: str = Depends(current_user), db: Session = Depends(get_db)):
    """Project details for the 'Log sources' page (signed-in users only)."""
    p = db.scalar(select(Project).order_by(Project.id).limit(1))
    return {"id": p.id if p else None, "name": p.name if p else settings.project_name,
            "ingest_api_key": settings.ingest_api_key,
            "endpoints": {"events": "/api/v1/ingest", "file": "/api/v1/ingest/text",
                          "deployments": "/api/v1/deployments"}}

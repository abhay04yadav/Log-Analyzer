"""S1 - Ingestion API (authenticated with a per-project API key).

The endpoint only validates and publishes to the event bus; it returns 202 immediately.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.bus import RAW_STREAM, get_bus
from app.core.config import get_settings
from app.core.security import project_from_api_key
from app.db import get_db
from app.models import Deployment, Project
from app.pipeline.normalize import _parse_ts

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

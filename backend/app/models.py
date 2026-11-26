"""Persistent data model.

Project ─┬─ LogEvent (normalised evidence, S2)        ErrorSignature (fingerprints, S3)
         ├─ Deployment (change evidence)              KnownError (playbook / known signatures)
         └─ Incident (S4) ─┬─ Candidate (S5/S6 ranked root causes)
                           ├─ Recommendation (S7, playbook / rules / LLM + validation)
                           └─ Feedback (S8, updates ranking weights)
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, JSONType, utcnow


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    api_key_hash: Mapped[str] = mapped_column(
        String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class LogEvent(Base):
    __tablename__ = "log_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id"), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime, index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    service: Mapped[str] = mapped_column(String(120), index=True)
    level: Mapped[str] = mapped_column(String(16), index=True)
    message: Mapped[str] = mapped_column(Text)
    logger: Mapped[str | None] = mapped_column(String(200))
    host: Mapped[str | None] = mapped_column(String(120))
    trace_id: Mapped[str | None] = mapped_column(String(64), index=True)
    span_id: Mapped[str | None] = mapped_column(String(64))
    parent_span_id: Mapped[str | None] = mapped_column(String(64))
    request_id: Mapped[str | None] = mapped_column(String(64))
    is_error: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    error_type: Mapped[str | None] = mapped_column(String(200))
    fingerprint: Mapped[str | None] = mapped_column(String(16), index=True)
    stack: Mapped[list | None] = mapped_column(
        JSONType)          # frames, innermost first
    stack_text: Mapped[str | None] = mapped_column(Text)
    attrs: Mapped[dict | None] = mapped_column(JSONType)
    source_format: Mapped[str] = mapped_column(
        String(16))         # json | logfmt | text
    raw: Mapped[str | None] = mapped_column(
        Text)                  # masked original
    incident_id: Mapped[int | None] = mapped_column(
        ForeignKey("incidents.id"), index=True)

    __table_args__ = (Index("ix_log_events_project_ts", "project_id", "ts"),)


class Deployment(Base):
    __tablename__ = "deployments"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id"), index=True)
    service: Mapped[str] = mapped_column(String(120), index=True)
    version: Mapped[str] = mapped_column(String(60))
    commit: Mapped[str | None] = mapped_column(String(60))
    author: Mapped[str | None] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    changed_files: Mapped[list | None] = mapped_column(JSONType)
    ts: Mapped[datetime] = mapped_column(DateTime, index=True)


class KnownError(Base):
    __tablename__ = "known_errors"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    # regex on "ErrorType: message"
    pattern: Mapped[str] = mapped_column(Text)
    # dependency | resource | security | ...
    category: Mapped[str] = mapped_column(String(40))
    severity: Mapped[str] = mapped_column(String(16))
    root_cause: Mapped[str] = mapped_column(Text)
    fix_steps: Mapped[list] = mapped_column(JSONType)


class ErrorSignature(Base):
    __tablename__ = "error_signatures"
    fingerprint: Mapped[str] = mapped_column(String(16), primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id"), index=True)
    service: Mapped[str] = mapped_column(String(120))
    error_type: Mapped[str | None] = mapped_column(String(200))
    template: Mapped[str] = mapped_column(Text)
    first_seen: Mapped[datetime] = mapped_column(DateTime)
    last_seen: Mapped[datetime] = mapped_column(DateTime)
    count: Mapped[int] = mapped_column(Integer, default=0)
    known_error_id: Mapped[int | None] = mapped_column(
        ForeignKey("known_errors.id"))
    confirmed_root_cause: Mapped[int] = mapped_column(
        Integer, default=0)   # times confirmed by engineers


class Incident(Base):
    __tablename__ = "incidents"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    category: Mapped[str] = mapped_column(
        String(20))              # error | security
    status: Mapped[str] = mapped_column(
        String(20), default="open")  # open | resolved
    severity: Mapped[str] = mapped_column(String(16), default="medium")
    detection: Mapped[list] = mapped_column(
        JSONType, default=list)  # why it was opened
    group_key: Mapped[str | None] = mapped_column(
        String(120))       # e.g. source IP for security
    window_start: Mapped[datetime] = mapped_column(DateTime)
    window_end: Mapped[datetime] = mapped_column(DateTime)
    services: Mapped[list] = mapped_column(JSONType, default=list)
    event_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    graph: Mapped[dict | None] = mapped_column(JSONType)
    similar: Mapped[list | None] = mapped_column(
        JSONType)          # similar confirmed past incidents
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    needs_recommendation: Mapped[bool] = mapped_column(Boolean, default=False)

    candidates: Mapped[list["Candidate"]] = relationship(
        back_populates="incident", cascade="all, delete-orphan", order_by="Candidate.rank")
    recommendations: Mapped[list["Recommendation"]] = relationship(
        back_populates="incident", cascade="all, delete-orphan", order_by="Recommendation.id.desc()")
    feedback: Mapped[list["Feedback"]] = relationship(
        back_populates="incident", cascade="all, delete-orphan", order_by="Feedback.id")


class Candidate(Base):
    __tablename__ = "candidates"
    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[int] = mapped_column(
        ForeignKey("incidents.id"), index=True)
    rank: Mapped[int] = mapped_column(Integer)
    service: Mapped[str] = mapped_column(String(120))
    fingerprint: Mapped[str | None] = mapped_column(String(16))
    error_type: Mapped[str | None] = mapped_column(String(200))
    message: Mapped[str] = mapped_column(Text)
    score: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(
        Float, default=0.0)   # magnitude of R + signal agreement
    confidence_detail: Mapped[dict | None] = mapped_column(JSONType)
    signals: Mapped[dict] = mapped_column(
        JSONType)                # T D A C H  in [0, 1]
    # human-readable explanation per signal
    reasons: Mapped[dict] = mapped_column(JSONType)
    event_ids: Mapped[list] = mapped_column(JSONType)
    first_seen: Mapped[datetime] = mapped_column(DateTime)
    count: Mapped[int] = mapped_column(Integer)
    code_location: Mapped[dict | None] = mapped_column(JSONType)
    deployment_id: Mapped[int | None] = mapped_column(Integer)
    known_error_id: Mapped[int | None] = mapped_column(Integer)
    verdict: Mapped[str | None] = mapped_column(
        String(20))        # confirmed | rejected

    incident: Mapped[Incident] = relationship(back_populates="candidates")


class Recommendation(Base):
    __tablename__ = "recommendations"
    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[int] = mapped_column(
        ForeignKey("incidents.id"), index=True)
    candidate_fingerprint: Mapped[str | None] = mapped_column(String(16))
    source: Mapped[str] = mapped_column(
        String(20))                # playbook | llm | rules
    model: Mapped[str | None] = mapped_column(String(80))
    summary: Mapped[str] = mapped_column(Text)
    root_cause: Mapped[str] = mapped_column(Text)
    fix_steps: Mapped[list] = mapped_column(JSONType)
    evidence_refs: Mapped[list] = mapped_column(JSONType)
    # evidence pack shown to the LLM
    evidence: Mapped[list] = mapped_column(JSONType)
    confidence: Mapped[float] = mapped_column(Float)
    validation: Mapped[dict] = mapped_column(
        JSONType)             # {status, issues}
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    incident: Mapped[Incident] = relationship(back_populates="recommendations")


class Feedback(Base):
    __tablename__ = "feedback"
    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[int] = mapped_column(
        ForeignKey("incidents.id"), index=True)
    candidate_id: Mapped[int | None] = mapped_column(Integer)
    verdict: Mapped[str] = mapped_column(
        String(20))               # confirmed | rejected
    note: Mapped[str | None] = mapped_column(Text)
    user: Mapped[str] = mapped_column(String(80))
    weights_before: Mapped[dict | None] = mapped_column(JSONType)
    weights_after: Mapped[dict | None] = mapped_column(JSONType)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    incident: Mapped[Incident] = relationship(back_populates="feedback")


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[dict] = mapped_column(JSONType)

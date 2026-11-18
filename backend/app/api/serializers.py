"""Model -> JSON helpers (timestamps are ISO-8601 UTC with a trailing Z)."""
from datetime import datetime

from app.models import Candidate, Deployment, Feedback, Incident, LogEvent, Recommendation


def iso(dt: datetime | None) -> str | None:
    return dt.isoformat(timespec="milliseconds") + "Z" if dt else None


def event_out(e: LogEvent, full: bool = False) -> dict:
    d = {"id": e.id, "ts": iso(e.ts), "service": e.service, "level": e.level, "message": e.message,
         "trace_id": e.trace_id, "span_id": e.span_id, "is_error": e.is_error, "error_type": e.error_type,
         "fingerprint": e.fingerprint, "incident_id": e.incident_id, "format": e.source_format,
         "has_stack": bool(e.stack_text)}
    if full:
        d.update(parent_span_id=e.parent_span_id, request_id=e.request_id, logger=e.logger, host=e.host,
                 stack=e.stack, stack_text=e.stack_text, attrs=e.attrs, raw=e.raw)
    return d


def incident_summary(i: Incident) -> dict:
    top = i.candidates[0] if i.candidates else None
    return {"id": i.id, "title": i.title, "category": i.category, "status": i.status, "severity": i.severity,
            "services": i.services, "event_count": i.event_count, "error_count": i.error_count,
            "window_start": iso(i.window_start), "window_end": iso(i.window_end), "created_at": iso(i.created_at),
            "top_candidate": {"service": top.service, "error_type": top.error_type, "score": top.score}
            if top else None,
            "has_recommendation": bool(i.recommendations)}


def candidate_out(c: Candidate) -> dict:
    return {"id": c.id, "rank": c.rank, "service": c.service, "fingerprint": c.fingerprint,
            "error_type": c.error_type, "message": c.message, "score": c.score, "signals": c.signals,
            "reasons": c.reasons, "event_ids": c.event_ids[:50], "first_seen": iso(c.first_seen), "count": c.count,
            "code_location": c.code_location, "deployment_id": c.deployment_id, "known_error_id": c.known_error_id,
            "verdict": c.verdict}


def recommendation_out(r: Recommendation) -> dict:
    return {"id": r.id, "source": r.source, "model": r.model, "summary": r.summary, "root_cause": r.root_cause,
            "fix_steps": r.fix_steps, "evidence_refs": r.evidence_refs, "evidence": r.evidence,
            "confidence": r.confidence, "validation": r.validation, "latency_ms": r.latency_ms,
            "candidate_fingerprint": r.candidate_fingerprint, "created_at": iso(r.created_at)}


def deployment_out(d: Deployment) -> dict:
    return {"id": d.id, "service": d.service, "version": d.version, "commit": d.commit, "author": d.author,
            "description": d.description, "changed_files": d.changed_files, "ts": iso(d.ts)}


def feedback_out(f: Feedback) -> dict:
    return {"id": f.id, "candidate_id": f.candidate_id, "verdict": f.verdict, "note": f.note, "user": f.user,
            "weights_before": f.weights_before, "weights_after": f.weights_after, "created_at": iso(f.created_at)}

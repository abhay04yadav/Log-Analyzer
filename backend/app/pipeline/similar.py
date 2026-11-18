"""Historical incident retrieval (feeds the H signal and the evidence pack).

For a root-cause candidate, find earlier incidents whose root cause was *confirmed by an engineer*
and that look like the same problem:

    similarity = 1.0                                   if the fingerprint is identical
               = 0.25 * same_service + 0.75 * Jaccard(error tokens)   otherwise

Error tokens come from the error type and the message template (variable values removed), so
"QueuePool limit of size 5 reached" in two different services still matches.  This lexical
similarity is fully explainable; semantic embeddings are a drop-in upgrade for the same function.
"""
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Candidate, Incident
from app.pipeline.fingerprint import template

MIN_SIMILARITY = 0.4
STOP = {"the", "and", "for", "with", "from", "error", "exception", "failed", "returned", "num", "str", "hex",
        "uuid", "true", "false", "none", "null"}


def tokens(error_type: str | None, message: str) -> set[str]:
    text = f"{error_type or ''} {template(message or '')}".lower()
    return {t for t in re.split(r"[^a-z0-9]+", text) if len(t) >= 3 and t not in STOP}


def similarity(a: dict, b: Candidate) -> float:
    if a.get("fingerprint") and a["fingerprint"] == b.fingerprint:
        return 1.0
    ta, tb = tokens(a.get("error_type"), a.get("message", "")), tokens(b.error_type, b.message)
    if not ta or not tb:
        return 0.0
    jac = len(ta & tb) / len(ta | tb)
    return round(0.25 * (a.get("service") == b.service) + 0.75 * jac, 3)


def find_similar(db: Session, incident: Incident, cand: dict, limit: int = 3) -> list[dict]:
    rows = db.execute(
        select(Candidate, Incident).join(Incident, Candidate.incident_id == Incident.id).where(
            Candidate.verdict == "confirmed", Incident.id != incident.id,
            Incident.project_id == incident.project_id, Incident.created_at < incident.created_at)
        .order_by(Incident.id.desc()).limit(200)).all()
    out = []
    for c, inc in rows:
        s = similarity(cand, c)
        if s >= MIN_SIMILARITY:
            rec = inc.recommendations[0] if inc.recommendations else None
            out.append({"incident_id": inc.id, "title": inc.title, "similarity": s, "service": c.service,
                        "error_type": c.error_type, "resolved_at": inc.updated_at.isoformat() + "Z",
                        "fix": rec.summary if rec else None,
                        "fix_steps": (rec.fix_steps[:3] if rec else [])})
    out.sort(key=lambda x: (-x["similarity"], -x["incident_id"]))
    return out[:limit]

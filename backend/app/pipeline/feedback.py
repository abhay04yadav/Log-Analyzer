"""S8 - Learn from engineer feedback.

Confirming a candidate moves the ranking weights towards the signals that were strong for the true
root cause (relative to the other candidates); rejecting moves them away.  Weights stay >= 0.05 and
are renormalised to sum to 1, and every change is stored so it can be shown and explained.
The confirmed fingerprint is also remembered, which raises the H (history) signal next time.
"""
from sqlalchemy.orm import Session

from app.db import utcnow
from app.models import Candidate, ErrorSignature, Feedback, Incident, Setting
from app.pipeline.rank import DEFAULT_WEIGHTS, get_weights

LEARNING_RATE = 0.1
MIN_WEIGHT = 0.05


def _update(weights: dict, cand: Candidate, others: list[Candidate], direction: int) -> dict:
    new = {}
    for k, w in weights.items():
        mean_other = sum(o.signals.get(k, 0) for o in others) / len(others) if others else 0.0
        new[k] = max(MIN_WEIGHT, w + direction * LEARNING_RATE * (cand.signals.get(k, 0) - mean_other))
    total = sum(new.values())
    return {k: round(v / total, 4) for k, v in new.items()}


def apply_feedback(db: Session, incident: Incident, cand: Candidate | None, verdict: str, note: str | None,
                   user: str) -> Feedback:
    before = get_weights(db)
    after = before
    if cand is not None:
        others = [c for c in incident.candidates if c.id != cand.id]
        after = _update(before, cand, others, +1 if verdict == "confirmed" else -1)
        cand.verdict = verdict
        if verdict == "confirmed":
            incident.status = "resolved"
            if cand.fingerprint and (sig := db.get(ErrorSignature, cand.fingerprint)):
                sig.confirmed_root_cause += 1
        setting = db.get(Setting, "weights")
        history = (setting.value.get("history", []) if setting else [])[-49:]
        history.append({"at": utcnow().isoformat() + "Z", "incident_id": incident.id, "verdict": verdict,
                        "weights": after})
        value = {"current": after, "default": DEFAULT_WEIGHTS, "history": history}
        if setting:
            setting.value = value
        else:
            db.add(Setting(key="weights", value=value))
    elif verdict == "resolved":
        incident.status = "resolved"
    fb = Feedback(incident_id=incident.id, candidate_id=cand.id if cand else None, verdict=verdict, note=note,
                  user=user, weights_before=before, weights_after=after)
    db.add(fb)
    incident.updated_at = utcnow()
    return fb

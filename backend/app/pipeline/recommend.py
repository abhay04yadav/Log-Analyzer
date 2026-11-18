"""S7 - Recommend a fix: evidence first, reasoning second.

Order of preference:
  1. playbook  - the top candidate matches a known error -> its curated fix (no AI needed)
  2. llm       - Gemini receives ONLY the evidence pack (masked events, signals, code, deployment)
                 and must cite evidence ids; the answer is then checked by the validator
  3. rules     - deterministic guidance when no AI provider is configured or the AI call fails

The validator rejects answers that cite unknown evidence, contain no steps, or propose dangerous
operations; such answers are kept but flagged "needs_review" so an engineer sees why.
"""
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Candidate, Deployment, Incident, KnownError, LogEvent, Recommendation
from app.pipeline.llm import LLMError, get_llm

settings = get_settings()

SYSTEM = (
    "You are a senior site-reliability engineer helping diagnose a production incident. "
    "Use ONLY the evidence provided. Every claim must cite evidence ids such as E1, E4. "
    "If the evidence is insufficient, say so and lower the confidence. "
    "Prefer safe, reversible actions (rollback, config change, feature flag) before code changes. "
    "Never suggest deleting data, disabling security controls or running destructive commands."
)
SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "summary": {"type": "STRING", "description": "one-sentence incident summary"},
        "root_cause": {"type": "STRING", "description": "most likely root cause with evidence ids"},
        "fix_steps": {"type": "ARRAY", "items": {"type": "STRING"}, "description": "ordered, concrete steps"},
        "evidence_refs": {"type": "ARRAY", "items": {"type": "STRING"}},
        "confidence": {"type": "NUMBER", "description": "0..1"},
    },
    "required": ["summary", "root_cause", "fix_steps", "evidence_refs", "confidence"],
}
DANGEROUS = re.compile(r"(?i)(rm\s+-rf|drop\s+(table|database)|truncate\s+table|chmod\s+777|"
                       r"disable\s+(auth|authentication|tls|ssl|firewall)|--no-verify|delete\s+from\s+\w+\s*;?$)")


# ---------------------------------------------------------------- evidence pack
def build_evidence(db: Session, incident: Incident, cand: Candidate) -> list[dict]:
    ev: list[dict] = []

    def add(kind, text, **ref):
        ev.append({"id": f"E{len(ev) + 1}", "kind": kind, "text": text[:1500], **ref})

    add("candidate", f"Top-ranked root-cause candidate: {cand.error_type or 'error'} in {cand.service} "
                     f"(score {cand.score:.2f}; signals {cand.signals}; reasons {cand.reasons})")
    first = db.get(LogEvent, cand.event_ids[0]) if cand.event_ids else None
    if first:
        add("event", f"[{first.ts.isoformat()}Z] {first.level} {first.service}: {first.message}"
                     + (f"\n{first.stack_text[:1200]}" if first.stack_text else ""), event_id=first.id)
    # first error of every other service = how the failure propagated
    others = db.scalars(select(LogEvent).where(LogEvent.incident_id == incident.id, LogEvent.is_error.is_(True))
                        .order_by(LogEvent.ts)).all()
    seen = {cand.service}
    for e in others:
        if e.service not in seen and len(ev) < 10:
            seen.add(e.service)
            add("event", f"[{e.ts.isoformat()}Z] {e.level} {e.service}: {e.message}", event_id=e.id)
    # a few warnings right before the first error often explain it (pool usage, retries, ...)
    if first:
        warns = db.scalars(select(LogEvent).where(
            LogEvent.incident_id == incident.id, LogEvent.level == "WARN", LogEvent.service == cand.service)
            .order_by(LogEvent.ts).limit(3)).all()
        for w in warns:
            add("event", f"[{w.ts.isoformat()}Z] WARN {w.service}: {w.message}", event_id=w.id)
    if cand.code_location and cand.code_location.get("resolved"):
        loc = cand.code_location
        numbered = "\n".join(f"{loc['start_line'] + i:>4}  {ln}" for i, ln in enumerate(loc["snippet"]))
        add("code", f"{loc['repo_path']} line {loc['line']} in {loc['function']}:\n{numbered}",
            file=loc["repo_path"], line=loc["line"])
    if cand.deployment_id and (d := db.get(Deployment, cand.deployment_id)):
        add("deployment", f"{d.service} {d.version} (commit {d.commit}) deployed at {d.ts.isoformat()}Z by "
                          f"{d.author}: {d.description}. Changed files: {', '.join(d.changed_files or [])}",
            deployment_id=d.id)
    for s in (incident.similar or [])[:2]:      # what fixed the same problem before
        add("history", f"Similar past incident #{s['incident_id']} ({s['title']}), similarity {s['similarity']:.2f}, "
                       f"root cause confirmed by an engineer. Fix used then: {s.get('fix') or 'n/a'}; "
                       f"steps: {'; '.join(s.get('fix_steps') or [])}", incident_id=s["incident_id"])
    add("graph", "Service graph edges (caller -> callee, calls/errors): " + "; ".join(
        f"{e['source']}->{e['target']} {e['calls']}/{e['errors']}" for e in (incident.graph or {}).get("edges", [])))
    return ev


# ---------------------------------------------------------------- validator
def validate(answer: dict, evidence: list[dict]) -> dict:
    issues, ids = [], {e["id"] for e in evidence}
    refs = [str(r).strip() for r in answer.get("evidence_refs") or []]
    cited = set(re.findall(r"\bE\d+\b", " ".join([answer.get("root_cause", "")] + list(answer.get("fix_steps", [])))))
    unknown = sorted((set(refs) | cited) - ids)
    if unknown:
        issues.append(f"cites evidence that does not exist: {', '.join(unknown)}")
    if not (set(refs) | cited) & ids:
        issues.append("no supporting evidence cited")
    steps = answer.get("fix_steps") or []
    if not steps:
        issues.append("no fix steps")
    for s in steps:
        if DANGEROUS.search(str(s)):
            issues.append(f"unsafe step blocked: {str(s)[:80]}")
    try:
        conf = float(answer.get("confidence", 0))
    except (TypeError, ValueError):
        conf = 0.0
    if not 0 <= conf <= 1:
        issues.append("confidence outside 0..1")
    return {"status": "passed" if not issues else "needs_review", "issues": issues}


# ---------------------------------------------------------------- deterministic fallback
RULES = [
    (r"(?i)pool|too many connections|connection.*timed? ?out", "Database connection pool exhausted",
     ["Check pool size / max-overflow settings against the number of workers",
      "Look for connections that are not returned to the pool (missing close / context manager)",
      "Roll back the latest deployment of the service if it changed database access code",
      "Add pool usage metrics and an alert before the pool is saturated"]),
    (r"(?i)NullPointer|NoneType|undefined is not|cannot read propert", "Unexpected null / missing value",
     ["Inspect the failing line and the object that is null", "Add a guard or default for the missing value",
      "Roll back the latest deployment if the change introduced the regression",
      "Add a unit test for the missing-data case"]),
    (r"(?i)refused|unreachable|ECONNREFUSED|No route", "Dependency unreachable",
     ["Check health and recent restarts of the dependency", "Verify host/port configuration and network policy",
      "Enable retries with backoff and a circuit breaker for the dependency"]),
    (r"(?i)memory|OOM", "Memory exhaustion",
     ["Check memory limits and recent traffic", "Capture a heap profile", "Scale out or raise limits temporarily"]),
    (r"(?i)timeout|timed out|deadline", "Downstream timeout",
     ["Identify the slow dependency from the service graph", "Review timeout and retry budgets",
      "Add caching or back-pressure for the slow call"]),
]


def rules_answer(cand: Candidate, evidence: list[dict], incident: Incident) -> dict:
    text = f"{cand.error_type} {cand.message}"
    title, steps = "Unclassified failure", ["Inspect the first failing event and its stack trace",
                                            "Compare with the most recent deployment of the service"]
    for rx, t, s in RULES:
        if re.search(rx, text):
            title, steps = t, list(s)
            break
    refs = [evidence[1]["id"]] if len(evidence) > 1 else [evidence[0]["id"]]
    code = next((e for e in evidence if e["kind"] == "code"), None)
    dep = next((e for e in evidence if e["kind"] == "deployment"), None)
    if code:
        steps.insert(0, f"Review {cand.code_location['repo_path']}:{cand.code_location['line']} "
                        f"({cand.code_location['function']}) [{code['id']}]")
        refs.append(code["id"])
    if dep:
        refs.append(dep["id"])
    if incident.category == "security":
        title = "Brute-force login attempt"
    root = (f"{title}: {cand.error_type or 'error'} in {cand.service} is the earliest and deepest failure "
            f"[{refs[0]}]" + (f"; it follows a recent deployment [{dep['id']}]" if dep else "") + ".")
    return {"summary": f"{title} in {cand.service}", "root_cause": root, "fix_steps": steps,
            "evidence_refs": refs, "confidence": 0.5}


def playbook_answer(k: KnownError, evidence: list[dict]) -> dict:
    refs = [e["id"] for e in evidence if e["kind"] in ("event", "candidate")][:3]
    return {"summary": k.name, "root_cause": f"{k.root_cause} [{', '.join(refs)}]", "fix_steps": list(k.fix_steps),
            "evidence_refs": refs, "confidence": 0.9}


# ---------------------------------------------------------------- entry point
def recommend(db: Session, incident: Incident, force_llm: bool = False) -> Recommendation | None:
    if not incident.candidates:
        return None
    cand = incident.candidates[0]
    evidence = build_evidence(db, incident, cand)
    known = db.get(KnownError, cand.known_error_id) if cand.known_error_id else None
    source, model, latency, error = "rules", None, None, None

    if known and not force_llm:
        answer, source = playbook_answer(known, evidence), "playbook"
    else:
        llm = get_llm()
        answer = None
        if llm:
            prompt = (f"Incident: {incident.title}\nCategory: {incident.category}\n"
                      f"Services involved: {', '.join(incident.services)}\n\nEVIDENCE:\n" +
                      "\n\n".join(f"{e['id']} ({e['kind']}): {e['text']}" for e in evidence) +
                      "\n\nReturn JSON with summary, root_cause (cite evidence ids), fix_steps "
                      "(3-6 ordered concrete steps, cite ids where relevant), evidence_refs and confidence (0..1).")
            try:
                answer, latency = llm.generate_json(SYSTEM, prompt, SCHEMA)
                source, model = "llm", llm.model
            except LLMError as e:
                error = str(e)
        if answer is None:
            answer = playbook_answer(known, evidence) if known else rules_answer(cand, evidence, incident)
            source = "playbook" if known else "rules"

    validation = validate(answer, evidence)
    if error:
        validation["issues"] = validation["issues"] + [f"AI unavailable, used {source}: {error}"]
    try:
        confidence = max(0.0, min(1.0, float(answer.get("confidence", 0.5))))
    except (TypeError, ValueError):
        confidence = 0.5
    if validation["status"] != "passed":
        confidence = min(confidence, 0.4)
    rec = Recommendation(
        incident_id=incident.id, candidate_fingerprint=cand.fingerprint, source=source, model=model,
        summary=str(answer.get("summary", ""))[:1000], root_cause=str(answer.get("root_cause", ""))[:4000],
        fix_steps=[str(s)[:1000] for s in (answer.get("fix_steps") or [])][:10],
        evidence_refs=[str(r) for r in (answer.get("evidence_refs") or [])][:20], evidence=evidence,
        confidence=round(confidence, 2), validation=validation, latency_ms=latency)
    incident.recommendations.insert(0, rec)          # newest first, same order as the relationship
    incident.needs_recommendation = False
    db.flush()
    return rec

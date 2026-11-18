"""S6 - Diagnose: rank root-cause candidates.

Each distinct failure inside the incident (service + fingerprint) is a candidate, scored with

        R = w1*T + w2*D + w3*A + w4*C + w5*H        (all signals in [0, 1], weights sum to 1)

  T  temporal precedence  - how early this failure appeared relative to the first error
  D  dependency position  - deepest failing service (no failing downstream) + how many services it impacts
  A  anomaly              - rate of this fingerprint compared with its own baseline
  C  code & change        - stack resolved to repository code, recent deployment of the service,
                            failing file changed in that deployment
  H  history              - known-error signature, or confirmed as root cause in a past incident

Every signal keeps a short human-readable reason, so the ranking can be explained line by line.
Weights are adjusted by engineer feedback (S8, see feedback.py).
"""
import math
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Candidate, Deployment, ErrorSignature, Incident, KnownError, LogEvent, Setting
from app.pipeline.detect import is_auth_failure, match_known, source_ip
from app.pipeline.similar import find_similar
from app.pipeline.traceback import build_graph, code_location, reachable_upstream

settings = get_settings()
DEFAULT_WEIGHTS = {"T": 0.25, "D": 0.25, "A": 0.15, "C": 0.20, "H": 0.15}
SIGNAL_NAMES = {"T": "Happened first", "D": "Position in call chain", "A": "Unusual volume",
                "C": "Code & recent changes", "H": "Seen before"}


def get_weights(db: Session) -> dict:
    s = db.get(Setting, "weights")
    return dict(s.value["current"]) if s else dict(DEFAULT_WEIGHTS)


def _fmt_dt(seconds: float) -> str:
    return f"{seconds * 1000:.0f} ms" if seconds < 1 else f"{seconds:.1f} s"


def analyse(db: Session, incident: Incident) -> None:
    events = list(db.scalars(select(LogEvent).where(LogEvent.incident_id == incident.id).order_by(LogEvent.ts)))
    if not events:
        return
    incident.window_start, incident.window_end = events[0].ts, events[-1].ts
    incident.event_count = len(events)
    incident.services = sorted({e.service for e in events})
    errors = [e for e in events if e.is_error]
    incident.error_count = len(errors)
    graph = build_graph(events)
    incident.graph = graph
    weights = get_weights(db)
    known = list(db.scalars(select(KnownError)))

    if incident.category == "security":
        cands = _security_candidates(db, incident, events, known)
        if cands and cands[0]["signals"]["C"] >= 1.0:
            incident.severity = "critical"
    else:
        cands = _error_candidates(db, incident, errors, graph, known)

    for c in cands:
        c["score"] = round(sum(weights[k] * c["signals"][k] for k in weights), 4)
    cands.sort(key=lambda c: (-c["score"], c["first_seen"]))
    add_confidence(cands)

    incident.similar = cands[0].get("similar", []) if cands else []
    old = {(c.service, c.fingerprint): c.verdict for c in incident.candidates}
    incident.candidates.clear()
    db.flush()
    for i, c in enumerate(cands[:8], 1):
        c.pop("similar", None)
        incident.candidates.append(Candidate(rank=i, verdict=old.get((c["service"], c["fingerprint"])), **c))

    if cands:
        top = cands[0]
        if incident.category == "security":
            incident.title = f"Possible brute-force attack from {incident.group_key}"
        else:
            what = top["error_type"] or top["message"][:60]
            extra = len(incident.services) - 1
            impacted = f" (+{extra} service{'s' if extra > 1 else ''} impacted)" if extra > 0 else ""
            incident.title = f"{what} in {top['service']}{impacted}"
        if incident.category == "error" and len(graph["nodes"]) >= 3 and incident.severity in ("low", "medium"):
            incident.severity = "high"


def add_confidence(cands: list[dict]) -> None:
    """Confidence = magnitude of R + agreement between signals (+ separation from the runner-up).

    agreement  share of the 5 signals that independently point at this candidate (the candidate is
               strongest, or within 0.05 of the strongest, on that signal and the signal is >= 0.5)
    margin     how far the candidate is ahead of the next one, relative to its own score
    confidence = 0.5 * R + 0.3 * agreement + 0.2 * margin
    """
    if not cands:
        return
    best = {k: max(c["signals"][k] for c in cands) for k in DEFAULT_WEIGHTS}
    for i, c in enumerate(cands):
        supporting = [k for k in DEFAULT_WEIGHTS if c["signals"][k] >= 0.5 and c["signals"][k] >= best[k] - 0.05]
        agreement = len(supporting) / len(DEFAULT_WEIGHTS)
        nxt = cands[i + 1]["score"] if i + 1 < len(cands) else 0.0
        prev = cands[i - 1]["score"] if i > 0 else None
        if prev is not None:                       # not the top candidate: no lead over the others
            margin = 0.0
        else:
            margin = (c["score"] - nxt) / c["score"] if c["score"] > 0 else 0.0
        conf = min(1.0, 0.5 * c["score"] + 0.3 * agreement + 0.2 * margin)
        label = "high" if conf >= 0.75 else "medium" if conf >= 0.5 else "low"
        c["confidence"] = round(conf, 3)
        c["confidence_detail"] = {"magnitude": round(c["score"], 3), "agreement": round(agreement, 2),
                                  "margin": round(margin, 3), "supporting": supporting, "label": label}


def _error_candidates(db, incident, errors, graph, known) -> list[dict]:
    if not errors:
        return []
    groups: dict[tuple, list[LogEvent]] = {}
    for e in errors:
        groups.setdefault((e.service, e.fingerprint), []).append(e)
    t0 = min(e.ts for e in errors)
    nodes = {n["id"]: n for n in graph["nodes"]}
    n_services = max(1, len(nodes) - 1)
    span = max(1.0, (incident.window_end - incident.window_start).total_seconds())
    lookback = timedelta(minutes=settings.deployment_lookback_minutes)
    out = []
    for (service, fp), evs in groups.items():
        first = min(e.ts for e in evs)
        rep = next((e for e in evs if e.stack), evs[0])
        reasons = {}

        # T - temporal precedence
        dt = (first - t0).total_seconds()
        T = math.exp(-dt / 5.0)
        reasons["T"] = "this was the very first error" if dt == 0 else f"started {_fmt_dt(dt)} after the first error"

        # D - position in the dependency graph + blast radius
        node = nodes.get(service, {})
        impacted = reachable_upstream(graph, service)
        failing_down = [d for d in node.get("downstream", []) if nodes.get(d, {}).get("errors")]
        leaf = 1.0 if not failing_down else 0.2
        D = 0.7 * leaf + 0.3 * min(1.0, len(impacted) / n_services)
        reasons["D"] = ("nothing it depends on is failing, so the problem starts here" if not failing_down
                        else f"it calls {', '.join(failing_down)}, which is also failing")
        if impacted:
            reasons["D"] += f"; it affects {', '.join(sorted(impacted))}"

        # A - anomaly vs own baseline
        baseline = db.scalar(select(func.count()).where(
            LogEvent.project_id == incident.project_id, LogEvent.fingerprint == fp,
            LogEvent.ts < incident.window_start, LogEvent.ts >= incident.window_start - timedelta(minutes=30))) or 0
        expected = baseline * (span / 1800.0)
        ratio = len(evs) / (expected + 1.0)
        A = min(1.0, math.log2(1 + ratio) / math.log2(1 + 20))
        reasons["A"] = (f"{len(evs)} times; this error did not happen before" if baseline == 0
                        else f"{len(evs)} times vs about {expected:.1f} normally ({ratio:.1f}x more)")

        # C - code location + deployment proximity
        loc = code_location(service, rep.stack)
        deploy = db.scalars(select(Deployment).where(
            Deployment.project_id == incident.project_id, Deployment.service == service,
            Deployment.ts <= first, Deployment.ts >= first - lookback).order_by(Deployment.ts.desc())).first()
        C, why = 0.0, []
        if loc and loc.get("resolved"):
            C += 0.3
            why.append(f"error points to {loc['repo_path']} line {loc['line']} ({loc['function']})")
        elif loc:
            C += 0.1
            why.append(f"error points to {loc['file']} line {loc['line']} (file not in the code repository)")
        if deploy:
            mins = (first - deploy.ts).total_seconds() / 60
            C += 0.4
            why.append(f"new version {deploy.version} of {service} was released {mins:.0f} min earlier")
            changed = [f.replace("\\", "/") for f in (deploy.changed_files or [])]
            if loc and loc.get("resolved") and any(loc["repo_path"].endswith(f) or f.endswith(loc["repo_path"])
                                                   for f in changed):
                C += 0.3
                why.append("and the failing file was changed in that release")
                loc["changed_in_deployment"] = deploy.version
        C = min(1.0, C)
        reasons["C"] = "; ".join(why) or "no code location and no recent release"

        # H - history
        k = match_known(known, rep.error_type, rep.message)
        sig = db.get(ErrorSignature, fp) if fp else None
        if k:
            H, reasons["H"] = 1.0, f"matches a known issue: {k.name}"
        elif sig and sig.confirmed_root_cause:
            H, reasons["H"] = 0.8, f"confirmed as the root cause {sig.confirmed_root_cause} time(s) before"
        elif sig and sig.first_seen < incident.window_start - timedelta(minutes=10):
            H, reasons["H"] = 0.2, "seen before, but never confirmed as a root cause"
        else:
            H, reasons["H"] = 0.0, "never seen before"
        cand_key = {"service": service, "fingerprint": fp, "error_type": rep.error_type, "message": rep.message}
        similar = find_similar(db, incident, cand_key)
        if similar and not k:
            s = similar[0]
            h_sim = round(0.9 * s["similarity"], 3)
            if h_sim >= H:
                H = h_sim
                reasons["H"] = (f"looks like past incident #{s['incident_id']} "
                                f"(similarity {s['similarity']:.2f}"
                                + (f", fixed by: {s['fix']}" if s.get("fix") else "") + ")")

        out.append(dict(similar=similar,service=service, fingerprint=fp, error_type=rep.error_type, message=rep.message[:1000],
                        signals={"T": round(T, 3), "D": round(D, 3), "A": round(A, 3), "C": round(C, 3),
                                 "H": round(H, 3)},
                        reasons=reasons, event_ids=[e.id for e in evs][:200], first_seen=first, count=len(evs),
                        code_location=loc, deployment_id=deploy.id if deploy else None,
                        known_error_id=k.id if k else None))
    return out


def _security_candidates(db, incident, events, known) -> list[dict]:
    fails = [e for e in events if is_auth_failure(e)]
    if not fails:
        return []
    ip = incident.group_key or source_ip(fails[0])
    span = max(1.0, (fails[-1].ts - fails[0].ts).total_seconds())
    users = sorted({str((e.attrs or {}).get("username")) for e in fails if (e.attrs or {}).get("username")})
    # a successful login from the same source after the failures is the most important evidence
    later = db.scalars(select(LogEvent).where(
        LogEvent.project_id == incident.project_id, LogEvent.service == fails[0].service,
        LogEvent.ts >= fails[0].ts, LogEvent.ts <= fails[-1].ts + timedelta(minutes=10),
        LogEvent.incident_id.is_(None))).all()
    for e in later:
        if (e.attrs or {}).get("event") == "auth_success" and source_ip(e) == ip:
            e.incident_id = incident.id
            events.append(e)
    success = [e for e in events if (e.attrs or {}).get("event") == "auth_success" and source_ip(e) == ip]
    k = next((x for x in known if x.category == "security"), None)
    rate = len(fails) / span * 60
    reasons = {
        "T": "the first suspicious event; failed logins continued for "
             f"{span:.0f} seconds",
        "D": f"targets {fails[0].service}" + (f"; accounts tried: {', '.join(users)}" if users else ""),
        "A": f"{len(fails)} failed logins in {span:.0f} seconds ({rate:.0f} per minute) from one address",
        "C": ("a login from the same address then SUCCEEDED - the account may be compromised"
              if success else "no successful login from this address"),
        "H": f"matches a known issue: {k.name}" if k else "never seen before",
    }
    return [dict(service=fails[0].service, fingerprint=None, error_type="Repeated authentication failures",
                 message=f"{len(fails)} failed logins from {ip}", reasons=reasons,
                 signals={"T": 1.0, "D": 1.0, "A": round(min(1.0, rate / 30), 3), "C": 1.0 if success else 0.0,
                          "H": 1.0 if k else 0.0},
                 event_ids=[e.id for e in fails][:200], first_seen=fails[0].ts, count=len(fails),
                 code_location=None, deployment_id=None, known_error_id=k.id if k else None)]

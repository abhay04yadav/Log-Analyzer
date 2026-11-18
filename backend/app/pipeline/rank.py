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
from app.pipeline.traceback import build_graph, code_location, reachable_upstream

settings = get_settings()
DEFAULT_WEIGHTS = {"T": 0.25, "D": 0.25, "A": 0.15, "C": 0.20, "H": 0.15}
SIGNAL_NAMES = {"T": "Temporal precedence", "D": "Dependency position", "A": "Anomaly",
                "C": "Code & deployment", "H": "History"}


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

    old = {(c.service, c.fingerprint): c.verdict for c in incident.candidates}
    incident.candidates.clear()
    db.flush()
    for i, c in enumerate(cands[:8], 1):
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
        reasons["T"] = "first error in the incident" if dt == 0 else f"appeared {_fmt_dt(dt)} after the first error"

        # D - position in the dependency graph + blast radius
        node = nodes.get(service, {})
        impacted = reachable_upstream(graph, service)
        failing_down = [d for d in node.get("downstream", []) if nodes.get(d, {}).get("errors")]
        leaf = 1.0 if not failing_down else 0.2
        D = 0.7 * leaf + 0.3 * min(1.0, len(impacted) / n_services)
        reasons["D"] = ("deepest failing service (no failing dependency)" if not failing_down
                        else f"depends on failing {', '.join(failing_down)}")
        if impacted:
            reasons["D"] += f"; impacts {', '.join(sorted(impacted))}"

        # A - anomaly vs own baseline
        baseline = db.scalar(select(func.count()).where(
            LogEvent.project_id == incident.project_id, LogEvent.fingerprint == fp,
            LogEvent.ts < incident.window_start, LogEvent.ts >= incident.window_start - timedelta(minutes=30))) or 0
        expected = baseline * (span / 1800.0)
        ratio = len(evs) / (expected + 1.0)
        A = min(1.0, math.log2(1 + ratio) / math.log2(1 + 20))
        reasons["A"] = (f"{len(evs)} occurrences, new failure (no baseline)" if baseline == 0
                        else f"{len(evs)} occurrences vs ~{expected:.1f} expected ({ratio:.1f}x)")

        # C - code location + deployment proximity
        loc = code_location(service, rep.stack)
        deploy = db.scalars(select(Deployment).where(
            Deployment.project_id == incident.project_id, Deployment.service == service,
            Deployment.ts <= first, Deployment.ts >= first - lookback).order_by(Deployment.ts.desc())).first()
        C, why = 0.0, []
        if loc and loc.get("resolved"):
            C += 0.3
            why.append(f"stack resolved to {loc['repo_path']}:{loc['line']} ({loc['function']})")
        elif loc:
            C += 0.1
            why.append(f"stack frame {loc['file']}:{loc['line']} (not in repository snapshot)")
        if deploy:
            mins = (first - deploy.ts).total_seconds() / 60
            C += 0.4
            why.append(f"{service} {deploy.version} deployed {mins:.0f} min before")
            changed = [f.replace("\\", "/") for f in (deploy.changed_files or [])]
            if loc and loc.get("resolved") and any(loc["repo_path"].endswith(f) or f.endswith(loc["repo_path"])
                                                   for f in changed):
                C += 0.3
                why.append("failing file was changed in that deployment")
                loc["changed_in_deployment"] = deploy.version
        C = min(1.0, C)
        reasons["C"] = "; ".join(why) or "no code location or recent change"

        # H - history
        k = match_known(known, rep.error_type, rep.message)
        sig = db.get(ErrorSignature, fp) if fp else None
        if k:
            H, reasons["H"] = 1.0, f"matches known error: {k.name}"
        elif sig and sig.confirmed_root_cause:
            H, reasons["H"] = 0.8, f"confirmed as root cause {sig.confirmed_root_cause}x before"
        elif sig and sig.first_seen < incident.window_start - timedelta(minutes=10):
            H, reasons["H"] = 0.2, "seen before, never confirmed as a root cause"
        else:
            H, reasons["H"] = 0.0, "no history"

        out.append(dict(service=service, fingerprint=fp, error_type=rep.error_type, message=rep.message[:1000],
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
        "T": "first suspicious event of the incident; failures continued for "
             f"{span:.0f} s",
        "D": f"targets {fails[0].service}" + (f"; accounts tried: {', '.join(users)}" if users else ""),
        "A": f"{len(fails)} failures in {span:.0f} s ({rate:.0f}/min) from one source",
        "C": ("successful login from the same source after the failures - possible compromise"
              if success else "no successful login from this source"),
        "H": f"matches known pattern: {k.name}" if k else "no history",
    }
    return [dict(service=fails[0].service, fingerprint=None, error_type="Repeated authentication failures",
                 message=f"{len(fails)} failed logins from {ip}", reasons=reasons,
                 signals={"T": 1.0, "D": 1.0, "A": round(min(1.0, rate / 30), 3), "C": 1.0 if success else 0.0,
                          "H": 1.0 if k else 0.0},
                 event_ids=[e.id for e in fails][:200], first_seen=fails[0].ts, count=len(fails),
                 code_location=None, deployment_id=None, known_error_id=k.id if k else None)]

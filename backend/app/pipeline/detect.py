"""Detection: decides when a set of events deserves an incident.

Detectors (all deterministic, all explainable):
  * known      - error matches a known-error signature from the playbook
  * spike      - an error fingerprint's rate jumps well above its own baseline
  * critical   - CRITICAL / FATAL level event
  * security   - repeated authentication failures from one source within a short window
"""
import re
from dataclasses import dataclass, field
from datetime import timedelta
from functools import lru_cache

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import KnownError, LogEvent

SPIKE_WINDOW = timedelta(seconds=60)
BASELINE_WINDOW = timedelta(minutes=15)
SECURITY_WINDOW = timedelta(seconds=120)
SECURITY_THRESHOLD = 5
AUTH_FAIL = re.compile(r"(?i)(login failed|authentication failed|invalid (password|credentials)|"
                       r"unauthori[sz]ed|bad credentials|401 unauthorized)")
IP = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")


@dataclass
class Detection:
    kind: str                       # known | spike | critical | security
    category: str                   # error | security
    label: str
    event_ids: list[int] = field(default_factory=list)
    fingerprint: str | None = None
    known_error_id: int | None = None
    severity: str = "medium"
    group_key: str | None = None


@lru_cache(maxsize=512)
def _rx(pattern: str):
    return re.compile(pattern)


def match_known(known: list[KnownError], error_type: str | None, message: str) -> KnownError | None:
    text = f"{error_type or ''}: {message}"
    for k in known:
        if _rx(k.pattern).search(text):
            return k
    return None


def source_ip(ev: LogEvent) -> str | None:
    attrs = ev.attrs or {}
    for k in ("client_ip", "source_ip", "remote_addr", "ip", "src_ip"):
        if attrs.get(k):
            return str(attrs[k])
    m = IP.search(ev.message or "")
    return m.group(0) if m else None


def is_auth_failure(ev: LogEvent) -> bool:
    attrs = ev.attrs or {}
    return attrs.get("event") == "auth_failure" or bool(AUTH_FAIL.search(ev.message or ""))


def detect(db: Session, project_id: int, events: list[LogEvent], known: list[KnownError]) -> list[Detection]:
    out: list[Detection] = []
    app_known = [k for k in known if k.category != "security"]
    errors = [e for e in events if e.is_error]

    # known signatures + critical level
    for e in errors:
        k = match_known(app_known, e.error_type, e.message)
        if k:
            out.append(Detection("known", "error", f"Known error: {k.name}", [e.id], e.fingerprint, k.id, k.severity))
        elif e.level == "CRITICAL":
            out.append(Detection("critical", "error", f"Critical error in {e.service}", [e.id], e.fingerprint,
                                 severity="high"))

    # rate spike per fingerprint (compared with the fingerprint's own baseline)
    by_fp: dict[str, list[LogEvent]] = {}
    for e in errors:
        if e.fingerprint:
            by_fp.setdefault(e.fingerprint, []).append(e)
    for fp, evs in by_fp.items():
        now = max(e.ts for e in evs)
        recent = db.scalar(select(func.count()).where(
            LogEvent.project_id == project_id, LogEvent.fingerprint == fp, LogEvent.ts > now - SPIKE_WINDOW))
        baseline = db.scalar(select(func.count()).where(
            LogEvent.project_id == project_id, LogEvent.fingerprint == fp,
            LogEvent.ts <= now - SPIKE_WINDOW, LogEvent.ts > now - SPIKE_WINDOW - BASELINE_WINDOW))
        per_min = baseline / (BASELINE_WINDOW / SPIKE_WINDOW)
        if recent >= 3 and recent > 3 * per_min + 2:
            out.append(Detection("spike", "error",
                                 f"Errors jumped in {evs[0].service}: {recent} per minute "
                                 + (f"(normally {per_min:.1f})" if per_min else "(normally none)"),
                                 [e.id for e in evs], fp, severity="high" if recent >= 10 else "medium"))

    # security: repeated authentication failures from one source
    fails: dict[str, list[LogEvent]] = {}
    for e in events:
        if is_auth_failure(e) and (ip := source_ip(e)):
            fails.setdefault(ip, []).append(e)
    for ip, evs in fails.items():
        now = max(e.ts for e in evs)
        window = db.scalars(select(LogEvent).where(
            LogEvent.project_id == project_id, LogEvent.ts > now - SECURITY_WINDOW,
            LogEvent.level.in_(("WARN", "ERROR", "CRITICAL")))).all()
        hits = [w for w in window if is_auth_failure(w) and source_ip(w) == ip]
        if len(hits) >= SECURITY_THRESHOLD:
            out.append(Detection("security", "security",
                                 f"{len(hits)} failed logins from {ip} within "
                                 f"{int(SECURITY_WINDOW.total_seconds())} seconds",
                                 [h.id for h in hits], severity="high", group_key=ip))
    return out

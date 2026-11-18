"""Initial data: demo project + known-error playbook + default ranking weights."""
from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import hash_api_key
from app.db import SessionLocal
from app.models import KnownError, Project, Setting
from app.pipeline.rank import DEFAULT_WEIGHTS

PLAYBOOK = [
    dict(name="Cache backend unreachable", category="dependency", severity="high",
         pattern=r"(?i)(redis|memcached|cache).*(connection refused|error 111|timed out|unreachable)",
         root_cause="The service cannot reach its cache backend (Redis); requests that depend on the cache fail.",
         fix_steps=["Check the cache container/pod status and restart events (kubectl get pods / docker ps)",
                    "Verify the cache host, port and network policy used by the service",
                    "Enable a cache-bypass fallback so requests degrade gracefully instead of failing",
                    "Add a health check and an alert on cache connection errors"]),
    dict(name="Out of memory", category="resource", severity="critical",
         pattern=r"(?i)(OutOfMemoryError|MemoryError|OOMKilled|out of memory)",
         root_cause="The process exceeded its memory limit.",
         fix_steps=["Check memory limits and the traffic level at the time of failure",
                    "Capture a heap dump / memory profile to find the growing allocation",
                    "Temporarily raise the limit or scale out, then fix the leak"]),
    dict(name="Disk full", category="resource", severity="high", pattern=r"(?i)no space left on device",
         root_cause="The volume used by the service is full.",
         fix_steps=["Identify the largest directories on the volume", "Rotate / ship logs and clean temp files",
                    "Add disk-usage alerting at 80%"]),
    dict(name="TLS certificate expired", category="config", severity="high",
         pattern=r"(?i)certificate (has )?expired|CERT_HAS_EXPIRED",
         root_cause="A TLS certificate used by the service or its dependency has expired.",
         fix_steps=["Renew the certificate and reload the service", "Automate renewal (e.g. cert-manager)",
                    "Alert 14 days before expiry"]),
    dict(name="DNS resolution failure", category="dependency", severity="high",
         pattern=r"(?i)(name or service not known|UnknownHostException|getaddrinfo ENOTFOUND|NXDOMAIN)",
         root_cause="A dependency host name cannot be resolved.",
         fix_steps=["Verify the configured host name", "Check cluster DNS health", "Check recent config changes"]),
    dict(name="Brute-force login attempt", category="security", severity="high",
         pattern=r"(?i)(login failed|authentication failed|invalid (password|credentials))",
         root_cause="Many failed logins from a single source in a short time indicate a password-guessing attack.",
         fix_steps=["Temporarily block or rate-limit the source IP at the gateway / WAF",
                    "Check whether any login from that IP succeeded and, if so, reset that account's password "
                    "and revoke its sessions",
                    "Enable account lockout or progressive delays after repeated failures",
                    "Enforce MFA for privileged accounts"]),
]


def seed() -> None:
    s = get_settings()
    with SessionLocal() as db:
        if not db.scalar(select(Project).limit(1)):
            db.add(Project(name=s.demo_project_name, api_key_hash=hash_api_key(s.demo_api_key)))
        existing = {k.name for k in db.scalars(select(KnownError))}
        for p in PLAYBOOK:
            if p["name"] not in existing:
                db.add(KnownError(**p))
        if not db.get(Setting, "weights"):
            db.add(Setting(key="weights", value={"current": DEFAULT_WEIGHTS, "default": DEFAULT_WEIGHTS,
                                                 "history": []}))
        db.commit()

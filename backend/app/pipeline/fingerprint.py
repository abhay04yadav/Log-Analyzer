"""S3 - Stable error fingerprints.

Variable tokens (ids, numbers, IPs, quoted values ...) are replaced by placeholders so that the same
failure produces the same fingerprint even when request-specific values differ.  The fingerprint
also includes the top in-application stack frames (file + function, never line numbers, so a
small code edit does not split a group).
"""
import hashlib
import re

VARIABLE = [
    (re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I), "<uuid>"),
    (re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?\b"), "<ip>"),
    (re.compile(r"\b[\w.+-]+\*{0,3}@[\w.-]+\.\w+\b"), "<email>"),
    (re.compile(r"\b0x[0-9a-f]+\b", re.I), "<hex>"),
    (re.compile(r"\b[0-9a-f]{12,}\b", re.I), "<hex>"),
    (re.compile(r"'[^']*'|\"[^\"]*\""), "<str>"),
    (re.compile(r"\b\d+(?:\.\d+)?(?:ms|s|m|h|kb|mb|gb|%)?\b", re.I), "<num>"),
]
FRAMEWORK = ("site-packages", "dist-packages", "/usr/lib/python", "<frozen", "java.", "javax.", "jdk.", "sun.",
             "org.springframework", "org.apache", "org.hibernate", "com.zaxxer", "io.netty", "node_modules",
             "node:internal")


def template(message: str) -> str:
    t = message.splitlines()[0] if message else ""
    for rx, rep in VARIABLE:
        t = rx.sub(rep, t)
    return re.sub(r"\s+", " ", t).strip()[:500]


def is_app_frame(frame: dict) -> bool:
    where = f"{frame.get('module') or ''} {frame.get('file') or ''}"
    return not any(f in where for f in FRAMEWORK)


def fingerprint(service: str, error_type: str | None, message: str, frames: list[dict] | None) -> str:
    app_frames = [f for f in (frames or []) if is_app_frame(f)][:3]
    frame_key = "|".join(f"{(f.get('file') or '').rsplit('/', 1)[-1]}:{f.get('function')}" for f in app_frames)
    # with a stack trace the frames identify the failure; the message template is only a tie-breaker
    msg_key = template(message) if not app_frames else template(message)[:80]
    key = f"{service}|{error_type or ''}|{frame_key}|{msg_key}"
    return hashlib.sha1(key.encode()).hexdigest()[:12]

"""Authentication helpers.

* Dashboard users: username/password -> HMAC-signed bearer token with expiry.
* Log producers: per-project API key (only its SHA-256 hash is stored).
* Ingestion rate limiting: sliding one-minute window per API key.
"""
import base64
import hashlib
import hmac
import json
import secrets
import threading
import time
from collections import defaultdict, deque

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db import get_db
from app.models import Project

settings = get_settings()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def create_token(username: str) -> str:
    payload = _b64(json.dumps({"sub": username, "exp": int(time.time()) + settings.token_ttl_minutes * 60}).encode())
    sig = _b64(hmac.new(settings.secret_key.encode(), payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{sig}"


def verify_token(token: str) -> str | None:
    try:
        payload, sig = token.split(".")
        good = _b64(hmac.new(settings.secret_key.encode(), payload.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, good):
            return None
        data = json.loads(_unb64(payload))
        return data["sub"] if data["exp"] > time.time() else None
    except (ValueError, KeyError, json.JSONDecodeError):
        return None


def check_password(username: str, password: str) -> bool:
    ok_user = hmac.compare_digest(username, settings.admin_username)
    ok_pass = hmac.compare_digest(password, settings.admin_password)
    return ok_user and ok_pass


def current_user(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    user = verify_token(authorization.split(" ", 1)[1])
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    return user


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def new_api_key() -> str:
    return "sla_" + secrets.token_urlsafe(24)


class RateLimiter:
    def __init__(self, per_minute: int):
        self.per_minute = per_minute
        self.hits: dict[str, deque] = defaultdict(deque)
        self.lock = threading.Lock()

    def allow(self, key: str, cost: int = 1) -> bool:
        now = time.monotonic()
        with self.lock:
            q = self.hits[key]
            while q and now - q[0] > 60:
                q.popleft()
            if len(q) + cost > self.per_minute:
                return False
            q.extend([now] * cost)
            return True


ingest_limiter = RateLimiter(settings.ingest_rate_per_minute)


def project_from_api_key(x_api_key: str | None = Header(default=None), db: Session = Depends(get_db)) -> Project:
    if not x_api_key:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing X-API-Key header")
    project = db.scalar(select(Project).where(Project.api_key_hash == hash_api_key(x_api_key)))
    if not project:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown API key")
    if not ingest_limiter.allow(project.api_key_hash):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Ingestion rate limit exceeded")
    return project

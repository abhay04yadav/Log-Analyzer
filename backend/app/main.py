"""FastAPI application: REST API + background pipeline worker."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, events, incidents, ingest, system
from app.bus import get_bus
from app.core.config import get_settings
from app.db import init_db
from app.pipeline.processor import Worker
from app.seed import seed

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    seed()
    get_bus()
    worker = Worker() if settings.run_worker else None
    if worker:
        worker.start()
    if not settings.llm_enabled:
        logging.getLogger("sla").warning("GEMINI_API_KEY not set: recommendations use playbooks + rules only")
    yield
    if worker:
        worker.shutdown()


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan,
              description="Evidence-first incident diagnosis: ingest -> normalise -> fingerprint -> correlate -> "
                          "traceback -> diagnose -> recommend -> learn.")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_list,
                   allow_origin_regex=settings.cors_origin_regex or None, allow_credentials=False,
                   allow_methods=["GET", "POST"], allow_headers=["Authorization", "Content-Type", "X-API-Key"])


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


for r in (auth.router, ingest.router, events.router, incidents.router, system.router):
    app.include_router(r)


@app.get("/health", tags=["system"])
def health():
    return {"status": "ok", "event_bus": get_bus().kind}

"""End-to-end pipeline tests: every simulator scenario must produce the expected root cause."""
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.api.ingest import store_deployment
from app.db import SessionLocal, init_db, utcnow
from app.main import app
from app.models import Candidate, Deployment, ErrorSignature, Feedback, Incident, LogEvent, Recommendation
from app.pipeline.normalize import normalise
from app.pipeline.processor import process_batch
from app.pipeline.recommend import recommend
from app.seed import seed
from app.simulator import scenarios

init_db()
seed()


@pytest.fixture(autouse=True)
def clean():
    with SessionLocal() as db:
        for m in (Feedback, Recommendation, Candidate, LogEvent, Incident, ErrorSignature, Deployment):
            db.execute(delete(m))
        db.commit()


def play(name: str):
    start = utcnow() - timedelta(seconds=40)
    steps = scenarios.build(name, start)
    with SessionLocal() as db:
        batch, t_end = [], 1.0
        for off, kind, item in steps:
            if kind == "deploy":
                store_deployment(db, 1, item)
                db.commit()
                continue
            if off > t_end:                       # 1-second batches, like the live simulator
                process_batch(db, 1, batch)
                batch, t_end = [], off + 1.0
            batch.append(item)
        if batch:
            process_batch(db, 1, batch)
        incs = db.scalars(select(Incident)).all()
        for inc in incs:
            recommend(db, inc)
        db.commit()
        return db.scalars(select(Incident).order_by(Incident.id)).all()


def test_normalise_formats():
    j = normalise({"timestamp": "2026-11-18T10:00:00Z", "level": "error", "service": "a", "message": "boom",
                   "password": "hunter2"})
    assert j["level"] == "ERROR" and j["service"] == "a" and j["attrs"]["password"] == "***"
    lf = normalise('ts=2026-11-18T10:00:00Z level=warn service=b msg="slow call" trace_id=abc')
    assert lf["level"] == "WARN" and lf["trace_id"] == "abc" and lf["source_format"] == "logfmt"
    tx = normalise("2026-11-18 10:00:00,123 ERROR [c] failed token=abcd1234 for x@example.com")
    assert tx["service"] == "c" and "abcd1234" not in tx["message"] and "x***@example.com" in tx["message"]


def test_db_pool_scenario():
    incs = [i for i in play("db_pool_exhaustion") if i.category == "error"]
    assert len(incs) == 1
    inc = incs[0]
    top = inc.candidates[0]
    assert top.service == "payment-service"
    assert "TimeoutError" in top.error_type
    assert top.code_location["resolved"] and top.code_location["repo_path"].endswith("payment/repository.py")
    assert "charge_card" in top.code_location["function"]
    assert top.deployment_id is not None and top.code_location.get("changed_in_deployment") == "v2.4.1"
    assert {"api-gateway", "checkout-service", "payment-service"} <= set(inc.services)
    rec = inc.recommendations[0]
    assert rec.source == "rules" and rec.validation["status"] == "passed"


def test_java_npe_scenario():
    incs = [i for i in play("inventory_null_pointer") if i.category == "error"]
    assert len(incs) == 1
    top = incs[0].candidates[0]
    assert top.service == "inventory-service" and "NullPointerException" in top.error_type
    assert top.code_location["resolved"] and top.code_location["function"] == "reserve"


def test_cache_playbook_scenario():
    incs = [i for i in play("cache_outage") if i.category == "error"]
    assert len(incs) == 1
    top = incs[0].candidates[0]
    assert top.service == "cart-service" and top.known_error_id is not None
    assert incs[0].recommendations[0].source == "playbook"


def test_security_scenario():
    incs = play("brute_force_login")
    sec = [i for i in incs if i.category == "security"]
    assert len(sec) == 1 and sec[0].group_key == "203.0.113.45"
    assert sec[0].candidates[0].signals["C"] == 1.0          # successful login after failures
    assert not [i for i in incs if i.category == "error"]


def test_api_flow_and_feedback():
    client = TestClient(app)
    assert client.get("/api/v1/incidents").status_code == 401
    r = client.post("/api/v1/auth/login", json={"username": "admin", "password": "wrong"})
    assert r.status_code == 401
    tok = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"}).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    assert client.post("/api/v1/ingest", json={"events": ["x"]}).status_code == 401
    assert client.post("/api/v1/ingest", json={"events": ["hello"]},
                       headers={"X-API-Key": "sla_demo_ingest_key"}).status_code == 202

    inc = [i for i in play("db_pool_exhaustion") if i.category == "error"][0]
    d = client.get(f"/api/v1/incidents/{inc.id}", headers=h).json()
    assert d["candidates"][0]["service"] == "payment-service" and d["graph"]["edges"]
    before = client.get("/api/v1/settings/weights", headers=h).json()["current"]
    r = client.post(f"/api/v1/incidents/{inc.id}/feedback", headers=h,
                    json={"verdict": "confirmed", "candidate_id": d["candidates"][0]["id"]})
    assert r.status_code == 200
    after = client.get("/api/v1/settings/weights", headers=h).json()["current"]
    assert after != before and abs(sum(after.values()) - 1) < 1e-3
    assert client.get(f"/api/v1/incidents/{inc.id}", headers=h).json()["status"] == "resolved"

"""End-to-end pipeline tests: every simulator scenario must produce the expected root cause."""
from datetime import timedelta
from pathlib import Path

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


def test_split_entries_keeps_stack_traces():
    from app.pipeline.normalize import split_entries

    text = ("2026-11-18 10:00:00 INFO [a] started\n"
            "2026-11-18 10:00:01 ERROR [a] failed\n"
            "Traceback (most recent call last):\n"
            '  File "/app/x.py", line 3, in run\n'
            "ValueError: boom\n"
            '{"level": "info", "message": "json line"}\n'
            "ts=2026-11-18T10:00:02Z level=warn msg=slow\n")
    entries = split_entries(text)
    assert len(entries) == 4 and "ValueError: boom" in entries[1]
    assert normalise(entries[1])["error_type"] == "ValueError"


def test_confidence_and_similar_incidents():
    client = TestClient(app)
    tok = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"}).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    first = [i for i in play("db_pool_exhaustion") if i.category == "error"][0]
    top = first.candidates[0]
    assert 0.5 <= top.confidence <= 1 and top.confidence_detail["label"] in ("high", "medium")
    assert "T" in top.confidence_detail["supporting"]
    client.post(f"/api/v1/incidents/{first.id}/feedback", headers=h,
                json={"verdict": "confirmed", "candidate_id": top.id})

    with SessionLocal() as db:                 # same failure again later -> history kicks in
        for m in (LogEvent,):
            db.execute(delete(m).where(LogEvent.incident_id.is_(None)))
        db.commit()
    incs = [i for i in play("db_pool_exhaustion") if i.category == "error" and i.id != first.id]
    assert len(incs) == 1
    second = incs[0]
    assert second.similar and second.similar[0]["incident_id"] == first.id
    assert second.candidates[0].signals["H"] >= 0.8
    assert f"#{first.id}" in second.candidates[0].reasons["H"]
    assert any(e["kind"] == "history" for e in second.recommendations[0].evidence)


def test_file_upload_endpoint():
    client = TestClient(app)
    tok = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"}).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    sample = (Path(__file__).resolve().parents[2] / "frontend/public/samples/shopflow-inventory-npe.log").read_text()
    assert client.post("/api/v1/upload", json={"content": sample}).status_code == 401
    r = client.post("/api/v1/upload", headers=h, json={"content": sample, "replay": True, "filename": "x.log"})
    assert r.status_code == 202 and r.json()["accepted"] > 100 and r.json()["replay_offset_seconds"] != 0
    r = client.post("/api/v1/ingest/text", headers={"X-API-Key": "sla_demo_ingest_key"},
                    json={"content": "2026-11-18 10:00:00 ERROR [svc] boom"})
    assert r.status_code == 202 and r.json()["accepted"] == 1

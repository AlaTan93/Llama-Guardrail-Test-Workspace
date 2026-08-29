"""API tests with a mocked pipeline (no GPU / LLM calls)."""

import asyncio

import pytest
from fastapi.testclient import TestClient

from src.web.app import app


@pytest.fixture
def client(monkeypatch, fixture_run):
    """TestClient with a fake pipeline job implementation."""

    async def fake_run_job(job):
        print(f"fake job {job.kind} started")
        job.emit({"type": "progress", "scorer": "attack", "done": 1, "total": 2})
        await asyncio.sleep(0.05)
        print("fake job done")

    from src.web import runners

    monkeypatch.setattr(runners, "run_job", fake_run_job)

    with TestClient(app) as c:
        c.fixture_run = fixture_run
        yield c


def _auth(client):
    return {"Authorization": f"Bearer {app.state.web_token}"}


def test_health_no_auth(client):
    assert client.get("/api/health").json() == {"ok": True}


def test_auth_required(client):
    assert client.get("/api/runs").status_code == 401
    assert client.get("/api/runs", headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_runs_listed(client):
    r = client.get("/api/runs", headers=_auth(client))
    assert r.status_code == 200
    assert r.json()["runs"][0]["name"] == client.fixture_run.name


def test_run_overview(client):
    r = client.get(f"/api/runs/{client.fixture_run.name}", headers=_auth(client))
    assert r.status_code == 200
    body = r.json()
    assert body["scorers"] == ["asr_claude", "strict_claude"]
    assert body["raw_count"] == 3


def test_run_404_and_bad_name(client):
    assert client.get("/api/runs/run_nope", headers=_auth(client)).status_code == 404
    # traversal protection is enforced in runstore.run_path (unit-tested);
    # httpx normalises dot-segments client-side, so we test the malformed-name path
    r = client.get("/api/runs/run_bad$slash", headers=_auth(client))
    assert r.status_code == 400


def test_prompts_filters(client):
    base = f"/api/runs/{client.fixture_run.name}/prompts"
    r = client.get(f"{base}?filter=errors", headers=_auth(client))
    assert r.json()["count"] == 1
    r = client.get(f"{base}?filter=bogus", headers=_auth(client))
    assert r.status_code == 400


def test_prompts_scorer_value_filter(client):
    url = f"/api/runs/{client.fixture_run.name}/prompts?scorer=asr_claude&value=true"
    r = client.get(url, headers=_auth(client))
    assert [row["conversation_id"] for row in r.json()["rows"]] == ["c1"]


def test_meta_patch(client, monkeypatch):
    import src.web.runs as runstore

    monkeypatch.setattr(runstore, "RESULTS_DIR", client.fixture_run.parent)
    r = client.patch(
        f"/api/runs/{client.fixture_run.name}/meta",
        headers=_auth(client),
        json={"tier": "Q4_K_M"},
    )
    assert r.status_code == 200
    assert r.json()["meta"]["tier"] == "Q4_K_M"

    empty = client.patch(
        f"/api/runs/{client.fixture_run.name}/meta", headers=_auth(client), json={}
    )
    assert empty.status_code == 400


def test_compare(client):
    name = client.fixture_run.name
    r = client.get(f"/api/compare?kind=asr&runs={name}", headers=_auth(client))
    assert r.status_code == 200
    body = r.json()
    assert body["columns"][0]["run"] == name
    assert any(m["metric"] == "total" for m in body["metrics"])


def test_job_validation_errors(client):
    h = _auth(client)
    assert client.post("/api/jobs", headers=h, json={"kind": "nope"}).status_code == 400
    assert (
        client.post("/api/jobs", headers=h, json={"kind": "e2e", "params": {}}).status_code == 400
    )
    r = client.post(
        "/api/jobs", headers=h,
        json={"kind": "rescore", "params": {"run_name": "run_missing", "models": ["asr_claude"]}},
    )
    assert r.status_code == 400
    assert "run not found" in r.json()["detail"]


def test_job_roundtrip_with_queue(client, monkeypatch):
    """summarize job runs through the real manager with a fake pipeline."""
    import src.web.runs as runstore

    monkeypatch.setattr(runstore, "RESULTS_DIR", client.fixture_run.parent)

    h = _auth(client)
    r = client.post(
        "/api/jobs", headers=h,
        json={"kind": "summarize", "params": {"run_name": client.fixture_run.name}},
    )
    assert r.status_code == 200
    job_id = r.json()["id"]

    for _ in range(50):
        rec = client.get(f"/api/jobs/{job_id}", headers=h).json()
        if rec["status"] in ("done", "error", "cancelled"):
            break
        import time

        time.sleep(0.1)
    assert rec["status"] == "done", rec.get("error")

    events = client.get(f"/api/jobs/{job_id}", headers=h).json()["recent_events"]
    types = [e["type"] for e in events]
    assert "log" in types  # stdout capture worked (fake job printed)
    assert types[-1] == "status" and events[-1]["status"] == "done"

    # SSE endpoint also requires token
    assert client.get(f"/api/jobs/{job_id}/events").status_code == 401


def test_cancel_unknown_job(client):
    r = client.post("/api/jobs/job_nope/cancel", headers=_auth(client))
    assert r.status_code == 400

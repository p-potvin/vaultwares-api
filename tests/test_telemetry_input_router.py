from fastapi import FastAPI
from fastapi.testclient import TestClient


def _client(monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "0")
    monkeypatch.setenv("VW_TELEMETRY_REQUIRE_KEY", "0")
    from app.routers.telemetry import input as input_router

    app = FastAPI()
    app.include_router(input_router.router)
    return TestClient(app), input_router


def _batch(batch_id="batch-1", event_id="event-1"):
    return {
        "schema_version": 1,
        "source": "agent-ledger-input-tracker",
        "host": {"hostname": "test"},
        "session_id": "session-1",
        "batch_id": batch_id,
        "started_at": "2026-06-07T10:00:00Z",
        "ended_at": "2026-06-07T10:01:00Z",
        "events": [
            {
                "event_id": event_id,
                "event_type": "minute_rollup",
                "timestamp": "2026-06-07T10:01:00Z",
                "bucket_start": "2026-06-07T10:00:00Z",
                "metrics": {"keystrokes": 42, "chars_typed": 20},
                "dimensions": {"focus_category": "editor"},
            }
        ],
    }


def test_ingest_batch_validates_and_stores(monkeypatch):
    client, input_router = _client(monkeypatch)

    async def fake_store(batch):
        assert batch["batch_id"] == "batch-1"
        assert batch["events"][0]["event_type"] == "minute_rollup"
        return {"batch_id": "batch-1", "inserted": 1, "duplicates": 0, "received": 1}

    monkeypatch.setattr(input_router, "store_input_batch", fake_store)

    response = client.post("/api/telemetry/input/batches", json=_batch())

    assert response.status_code == 200
    assert response.json()["inserted"] == 1


def test_ingest_rejects_malformed_rows(monkeypatch):
    client, _ = _client(monkeypatch)
    payload = _batch()
    payload["events"][0]["metrics"] = ["not", "object"]

    response = client.post("/api/telemetry/input/batches", json=payload)

    assert response.status_code == 422


def test_ingest_requires_key_when_configured(monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "1")
    monkeypatch.setenv("VW_TELEMETRY_REQUIRE_KEY", "1")
    monkeypatch.setenv("VW_TELEMETRY_API_KEY", "expected")
    from app.routers.telemetry import input as input_router

    app = FastAPI()
    app.include_router(input_router.router)
    client = TestClient(app)

    response = client.post("/api/telemetry/input/batches", json=_batch())
    assert response.status_code == 401

    async def fake_store(batch):
        return {"batch_id": batch["batch_id"], "inserted": 1, "duplicates": 0, "received": 1}

    monkeypatch.setattr(input_router, "store_input_batch", fake_store)
    ok = client.post("/api/telemetry/input/batches", json=_batch("batch-2", "event-2"), headers={"x-api-key": "expected"})
    assert ok.status_code == 200

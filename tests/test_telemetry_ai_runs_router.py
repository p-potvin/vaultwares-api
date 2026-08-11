from fastapi import FastAPI
from fastapi.testclient import TestClient


def _client(monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "0")
    monkeypatch.delenv("VW_TELEMETRY_API_KEY", raising=False)
    from app.routers.telemetry import ai_runs as ai_runs_router

    app = FastAPI()
    app.include_router(ai_runs_router.router)
    return TestClient(app), ai_runs_router


def _batch(run_id="run-1", **overrides):
    run = {
        "run_id": run_id,
        "provider": "huggingface",
        "runtime": "hf-inference",
        "model": "Qwen/Qwen3.6-35B",
        "task": "chat",
        "project": "vault-inference",
        "started_at": "2026-08-09T10:00:00Z",
        "ended_at": "2026-08-09T10:00:02Z",
        "duration_ms": 2000.0,
        "ttft_ms": 180.0,
        "input_tokens": 120,
        "output_tokens": 480,
        "total_tokens": 600,
        "status": "ok",
    }
    run.update(overrides)
    return {
        "schema": 1,
        "source": "vw-ai-runs",
        "host": "Clopeux-Desktop",
        "collectedAt": "2026-08-09T10:00:05Z",
        "batchIndex": 0,
        "runs": [run],
    }


def test_ingest_batch_validates_and_stores(monkeypatch):
    client, router = _client(monkeypatch)
    seen = {}

    async def fake_store(batch):
        seen["batch"] = batch
        return {"batch_id": "abc", "stored": 1, "received": 1}

    monkeypatch.setattr(router, "store_run_batch", fake_store)

    response = client.post("/api/telemetry/ai-runs/batches", json=_batch())

    assert response.status_code == 200
    assert response.json()["stored"] == 1
    # The alias form is what the persistence layer reads.
    assert seen["batch"]["host"] == "Clopeux-Desktop"
    assert seen["batch"]["runs"][0]["run_id"] == "run-1"


def test_unknown_fields_survive_to_the_store(monkeypatch):
    # Recorders add KPIs faster than the API gains columns; extra keys must
    # reach the persistence layer so they can land in `extra` rather than 422.
    client, router = _client(monkeypatch)
    captured = {}

    async def fake_store(batch):
        captured["run"] = batch["runs"][0]
        return {"batch_id": "abc", "stored": 1, "received": 1}

    monkeypatch.setattr(router, "store_run_batch", fake_store)

    payload = _batch(sampler="euler", some_future_kpi=1.25)
    response = client.post("/api/telemetry/ai-runs/batches", json=payload)

    assert response.status_code == 200
    assert captured["run"]["sampler"] == "euler"
    assert captured["run"]["some_future_kpi"] == 1.25


def test_unknown_status_is_normalised_not_rejected(monkeypatch):
    client, router = _client(monkeypatch)
    captured = {}

    async def fake_store(batch):
        captured["run"] = batch["runs"][0]
        return {"batch_id": "abc", "stored": 1, "received": 1}

    monkeypatch.setattr(router, "store_run_batch", fake_store)

    response = client.post("/api/telemetry/ai-runs/batches", json=_batch(status="exploded"))

    assert response.status_code == 200
    assert captured["run"]["status"] == "error"


def test_rejected_status_is_preserved(monkeypatch):
    # A budget-guard stop must stay distinguishable from a genuine failure.
    client, router = _client(monkeypatch)
    captured = {}

    async def fake_store(batch):
        captured["run"] = batch["runs"][0]
        return {"batch_id": "abc", "stored": 1, "received": 1}

    monkeypatch.setattr(router, "store_run_batch", fake_store)

    client.post("/api/telemetry/ai-runs/batches", json=_batch(status="rejected"))
    assert captured["run"]["status"] == "rejected"


def test_run_without_id_is_rejected(monkeypatch):
    client, _ = _client(monkeypatch)
    payload = _batch()
    del payload["runs"][0]["run_id"]

    response = client.post("/api/telemetry/ai-runs/batches", json=payload)

    assert response.status_code == 422


def test_negative_duration_is_rejected(monkeypatch):
    client, _ = _client(monkeypatch)

    response = client.post("/api/telemetry/ai-runs/batches", json=_batch(duration_ms=-5))

    assert response.status_code == 422


def test_empty_batch_is_rejected(monkeypatch):
    client, _ = _client(monkeypatch)
    payload = _batch()
    payload["runs"] = []

    response = client.post("/api/telemetry/ai-runs/batches", json=payload)

    assert response.status_code == 422


def test_ingest_requires_key_when_configured(monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "1")
    monkeypatch.setenv("VW_TELEMETRY_API_KEY", "s3cret")
    from app.routers.telemetry import ai_runs as router

    app = FastAPI()
    app.include_router(router.router)
    client = TestClient(app)

    assert client.post("/api/telemetry/ai-runs/batches", json=_batch()).status_code == 401
    assert client.post(
        "/api/telemetry/ai-runs/batches", json=_batch(), headers={"x-api-key": "wrong"}
    ).status_code == 401


def test_batch_size_cap_is_enforced(monkeypatch):
    monkeypatch.setenv("VW_AI_RUNS_BATCH_MAX", "2")
    client, _ = _client(monkeypatch)
    payload = _batch()
    payload["runs"] = [dict(payload["runs"][0], run_id=f"run-{i}") for i in range(3)]

    response = client.post("/api/telemetry/ai-runs/batches", json=payload)

    assert response.status_code == 422


def test_read_endpoints_pass_filters_through(monkeypatch):
    client, router = _client(monkeypatch)
    captured = {}

    async def fake_summary(days, filters):
        captured["days"] = days
        captured["filters"] = filters
        return {"totals": {}, "by_provider": []}

    monkeypatch.setattr(router, "get_summary", fake_summary)

    response = client.get(
        "/api/telemetry/ai-runs/summary",
        params={"days": 7, "provider": "huggingface", "project": "vault-inference"},
    )

    assert response.status_code == 200
    assert captured["days"] == 7
    assert captured["filters"] == {"provider": "huggingface", "project": "vault-inference"}


def test_timeline_rejects_out_of_range_days(monkeypatch):
    client, _ = _client(monkeypatch)
    assert client.get("/api/telemetry/ai-runs/timeline", params={"days": 0}).status_code == 422


def test_public_surface_batch_is_scrubbed_on_ingest(monkeypatch):
    # The sender already scrubs, but a Space's posting key can leak — filtering
    # only at the sender trusts a client we do not control.
    client, router = _client(monkeypatch)
    captured = {}

    async def fake_store(batch):
        captured["batch"] = batch
        return {"batch_id": "abc", "stored": 1, "received": 1}

    monkeypatch.setattr(router, "store_run_batch", fake_store)

    payload = _batch(host="Clopeux-Desktop", project="vaultwares-studio",
                     session_id="visitor-42", gpu_name="RTX 3060")
    payload["publicSurface"] = True

    client.post("/api/telemetry/ai-runs/batches", json=payload)

    run = captured["batch"]["runs"][0]
    for banned in ("project", "session_id", "gpu_name", "host"):
        assert banned not in run, f"{banned} survived the public scrub"
    assert captured["batch"]["host"].startswith("public:")
    assert run["model"] == "Qwen/Qwen3.6-35B"  # useful fields survive


def test_public_key_forces_scrub_even_without_the_flag(monkeypatch):
    # A leaked Space key must not be able to forge internal records simply by
    # omitting publicSurface — the key decides, not the client.
    monkeypatch.setenv("AUTH_ENABLED", "1")
    monkeypatch.setenv("VW_TELEMETRY_API_KEY", "internal-key")
    monkeypatch.setenv("VW_TELEMETRY_PUBLIC_API_KEY", "space-key")
    from app.routers.telemetry import ai_runs as router

    captured = {}

    async def fake_store(batch):
        captured["batch"] = batch
        return {"batch_id": "abc", "stored": 1, "received": 1}

    monkeypatch.setattr(router, "store_run_batch", fake_store)

    app = FastAPI()
    app.include_router(router.router)
    client = TestClient(app)

    payload = _batch(project="vaultwares-studio", session_id="visitor-42")
    # publicSurface deliberately absent
    response = client.post(
        "/api/telemetry/ai-runs/batches", json=payload, headers={"x-api-key": "space-key"}
    )

    assert response.status_code == 200
    assert "project" not in captured["batch"]["runs"][0]
    assert "session_id" not in captured["batch"]["runs"][0]


def test_internal_key_keeps_full_attribution(monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "1")
    monkeypatch.setenv("VW_TELEMETRY_API_KEY", "internal-key")
    monkeypatch.setenv("VW_TELEMETRY_PUBLIC_API_KEY", "space-key")
    from app.routers.telemetry import ai_runs as router

    captured = {}

    async def fake_store(batch):
        captured["batch"] = batch
        return {"batch_id": "abc", "stored": 1, "received": 1}

    monkeypatch.setattr(router, "store_run_batch", fake_store)

    app = FastAPI()
    app.include_router(router.router)
    client = TestClient(app)

    response = client.post(
        "/api/telemetry/ai-runs/batches",
        json=_batch(project="vault-inference"),
        headers={"x-api-key": "internal-key"},
    )

    assert response.status_code == 200
    assert captured["batch"]["runs"][0]["project"] == "vault-inference"
    assert captured["batch"]["host"] == "Clopeux-Desktop"


def test_prompt_hash_is_dropped_from_a_public_surface(monkeypatch):
    client, router = _client(monkeypatch)
    captured = {}

    async def fake_store(batch):
        captured["run"] = batch["runs"][0]
        return {"batch_id": "abc", "stored": 1, "received": 1}

    monkeypatch.setattr(router, "store_run_batch", fake_store)

    payload = _batch(prompt_hash="deadbeefdeadbeef")
    payload["publicSurface"] = True
    client.post("/api/telemetry/ai-runs/batches", json=payload)

    assert "prompt_hash" not in captured["run"]


# ── rollups + reconciliation ────────────────────────────────────────────────

def _rollup_batch(**overrides):
    entry = {
        "hour": "2026-08-10T14:00:00Z",
        "provider": "huggingface",
        "runtime": "hf-inference",
        "model": "Qwen/Qwen3.6-35B",
        "task": "chat",
        "project": "vault-inference",
        "host": "Clopeux-Desktop",
        "status": "ok",
        "runs": 42,
        "failures": 2,
        "total_tokens": 90000,
        "cost_usd": 0.0123,
        "duration_hist": [1, 2, 3, 4, 5, 6, 7, 8, 9, 1, 0, 0],
    }
    entry.update(overrides)
    return {
        "schema": 1,
        "source": "vw-ai-runs",
        "host": "Clopeux-Desktop",
        "collectedAt": "2026-08-10T15:00:05Z",
        "batchIndex": 0,
        "grain": "hour",
        "rollups": [entry],
    }


def test_rollup_batch_is_accepted(monkeypatch):
    client, router = _client(monkeypatch)
    captured = {}

    async def fake_store(batch):
        captured["batch"] = batch
        return {"batch_id": "abc", "stored": 1, "received": 1}

    monkeypatch.setattr(router, "store_rollup_batch", fake_store)

    response = client.post("/api/telemetry/ai-runs/rollups/batches", json=_rollup_batch())

    assert response.status_code == 200
    assert captured["batch"]["grain"] == "hour"
    assert captured["batch"]["rollups"][0]["runs"] == 42


def test_rollup_rejects_oversized_histogram(monkeypatch):
    # The bins go straight into a BIGINT[] column; the sender does not get to
    # choose the length.
    client, _ = _client(monkeypatch)
    response = client.post(
        "/api/telemetry/ai-runs/rollups/batches",
        json=_rollup_batch(duration_hist=list(range(64))),
    )
    assert response.status_code == 422


def test_rollup_rejects_negative_bins(monkeypatch):
    client, _ = _client(monkeypatch)
    response = client.post(
        "/api/telemetry/ai-runs/rollups/batches",
        json=_rollup_batch(duration_hist=[1, -5, 2]),
    )
    assert response.status_code == 422


def test_public_key_cannot_write_rollups(monkeypatch):
    # Rollup ingest is an overwrite, so a leaked Space key must not reach it —
    # it could otherwise rewrite the durable grain wholesale.
    monkeypatch.setenv("AUTH_ENABLED", "1")
    monkeypatch.setenv("VW_TELEMETRY_API_KEY", "internal-key")
    monkeypatch.setenv("VW_TELEMETRY_PUBLIC_API_KEY", "space-key")
    from app.routers.telemetry import ai_runs as router

    app = FastAPI()
    app.include_router(router.router)
    client = TestClient(app)

    response = client.post(
        "/api/telemetry/ai-runs/rollups/batches",
        json=_rollup_batch(),
        headers={"x-api-key": "space-key"},
    )
    assert response.status_code == 403


def test_public_key_cannot_settle_costs(monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "1")
    monkeypatch.setenv("VW_TELEMETRY_API_KEY", "internal-key")
    monkeypatch.setenv("VW_TELEMETRY_PUBLIC_API_KEY", "space-key")
    from app.routers.telemetry import ai_runs as router

    app = FastAPI()
    app.include_router(router.router)
    client = TestClient(app)

    response = client.post(
        "/api/telemetry/ai-runs/settle",
        json={"request_ids": ["req-1"], "cost_usd": 0.5},
        headers={"x-api-key": "space-key"},
    )
    assert response.status_code == 403


def test_settle_passes_ids_and_total_through(monkeypatch):
    client, router = _client(monkeypatch)
    captured = {}

    async def fake_settle(request_ids, cost_usd, billing_source=None):
        captured["ids"] = list(request_ids)
        captured["cost"] = cost_usd
        captured["source"] = billing_source
        return {"settled": 2, "skipped": 0, "per_row": cost_usd / 2}

    monkeypatch.setattr(router, "settle_costs", fake_settle)

    response = client.post(
        "/api/telemetry/ai-runs/settle",
        json={"request_ids": ["req-1", "req-2"], "cost_usd": 0.5,
              "billing_source": "hf-embeddings"},
    )

    assert response.status_code == 200
    assert captured["ids"] == ["req-1", "req-2"]
    assert captured["cost"] == 0.5
    # One settled total split across the rows it covers, not dumped on one.
    assert response.json()["per_row"] == 0.25


def test_settle_rejects_empty_id_list(monkeypatch):
    client, _ = _client(monkeypatch)
    response = client.post(
        "/api/telemetry/ai-runs/settle", json={"request_ids": [], "cost_usd": 1.0}
    )
    assert response.status_code == 422


def test_settle_rejects_negative_cost(monkeypatch):
    client, _ = _client(monkeypatch)
    response = client.post(
        "/api/telemetry/ai-runs/settle",
        json={"request_ids": ["req-1"], "cost_usd": -1.0},
    )
    assert response.status_code == 422


# ── SQL construction ────────────────────────────────────────────────────────
#
# The router tests above mock the persistence layer, so they cannot catch a
# malformed query. These assert on the generated SQL directly.

def test_day_window_does_not_use_string_concatenation():
    # `($1 || ' days')::interval` makes Postgres infer the parameter as TEXT,
    # so asyncpg rejects the int it is actually handed with a DataError. This
    # shipped once; make_interval is the type-safe form.
    from app.routers.telemetry.ai_runs_db import _where

    sql, params = _where(7, {})

    assert "|| ' days'" not in sql
    assert "make_interval" in sql
    assert params == [7]
    assert all(isinstance(p, int) for p in params)


def test_filters_are_parameterised_not_interpolated():
    from app.routers.telemetry.ai_runs_db import _where

    sql, params = _where(30, {"provider": "huggingface", "project": "vault-inference"})

    # Values must arrive as bind parameters; only $n placeholders in the SQL.
    assert "huggingface" not in sql
    assert "vault-inference" not in sql
    assert params == [30, "huggingface", "vault-inference"]
    assert "$1" in sql and "$2" in sql and "$3" in sql


def test_unknown_filter_keys_are_ignored():
    # Keys are looked up in a fixed map, so a caller cannot inject a predicate.
    from app.routers.telemetry.ai_runs_db import _where

    sql, params = _where(None, {"provider": "hf", "; DROP TABLE ai_runs;--": "x"})

    assert "DROP TABLE" not in sql
    assert params == ["hf"]


def test_timeline_bucket_is_whitelisted():
    # `bucket` is interpolated into date_trunc(), never parameterised, so an
    # unknown value must fall back rather than reach the query.
    import asyncio

    from app.routers.telemetry import ai_runs_db

    captured = {}

    class FakeConn:
        async def fetch(self, sql, *args):
            captured["sql"] = sql
            return []

    class FakeAcquire:
        async def __aenter__(self):
            return FakeConn()

        async def __aexit__(self, *a):
            return False

    class FakePool:
        def acquire(self):
            return FakeAcquire()

    async def fake_pool():
        return FakePool()

    async def noop_schema():
        return None

    original_pool = ai_runs_db.get_pool
    original_schema = ai_runs_db.ensure_schema
    ai_runs_db.get_pool = fake_pool
    ai_runs_db.ensure_schema = noop_schema
    try:
        asyncio.run(ai_runs_db.get_timeline("month'); DROP TABLE ai_runs;--", 30, {}))
    finally:
        ai_runs_db.get_pool = original_pool
        ai_runs_db.ensure_schema = original_schema

    assert "DROP TABLE" not in captured["sql"]
    assert "date_trunc('day'" in captured["sql"]  # fell back to the default

from fastapi import FastAPI
from fastapi.testclient import TestClient
from datetime import datetime, timezone


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


def test_focus_summary_uses_active_seconds_and_window_labels():
    from app.routers.telemetry import db

    rows = [
        {
            "metrics": {"active_seconds": 60},
            "dimensions": {"focus_category": "browser", "window_name": "Firefox"},
        },
        {
            "metrics": {"active_seconds": 30},
            "dimensions": {"focus_category": "browser", "window_name": "Explorer"},
        },
        {
            "metrics": {"active_seconds": 15},
            "dimensions": {"focus_category": "development", "window_name": "PowerShell"},
        },
    ]

    assert db._bucket_counts(rows, "focus_category")[0] == {"name": "browser", "count": 90.0}
    assert db._window_counts(rows)[:2] == [
        {"category": "browser", "name": "Firefox", "count": 60.0},
        {"category": "browser", "name": "Explorer", "count": 30.0},
    ]


def test_kpi_signals_derive_focus_typing_pointer_rhythm_and_reliability():
    from app.routers.telemetry import db

    rows = [
        {
            "timestamp": datetime(2026, 6, 7, 14, 1, tzinfo=timezone.utc),
            "bucket_start": datetime(2026, 6, 7, 14, 0, tzinfo=timezone.utc),
            "received_at": datetime(2026, 6, 7, 14, 2, tzinfo=timezone.utc),
            "metrics": {
                "active_seconds": 60,
                "keystrokes": 200,
                "chars_typed": 100,
                "chars_pasted": 300,
                "saves": 2,
                "undo_redo": 1,
                "shortcut_count": 10,
                "clicks": 20,
                "scroll_ticks": 40,
                "mouse_distance_m": 4,
                "context_switches": 2,
                "longest_focus_streak_seconds": 180,
                "focus_streak_seconds_total": 240,
                "focus_streak_samples": 2,
                "switch_recovery_seconds_total": 12,
                "switch_recovery_samples": 2,
                "longest_active_block_seconds": 600,
                "rest_gap_seconds_total": 900,
                "rest_gap_seconds_max": 900,
                "active_starts_after_rest": 1,
                "spool_backlog_batches": 3,
                "spool_backlog_bytes": 1200,
                "click_hotspots": {"4:8": 10, "2:1": 5},
            },
            "dimensions": {"focus_category": "browser", "window_name": "Firefox"},
        },
        {
            "timestamp": datetime(2026, 6, 7, 15, 1, tzinfo=timezone.utc),
            "bucket_start": datetime(2026, 6, 7, 15, 0, tzinfo=timezone.utc),
            "received_at": datetime(2026, 6, 7, 15, 2, tzinfo=timezone.utc),
            "metrics": {
                "active_seconds": 120,
                "keystrokes": 100,
                "chars_typed": 300,
                "chars_pasted": 100,
                "saves": 0,
                "undo_redo": 2,
                "shortcut_count": 5,
                "clicks": 10,
                "scroll_ticks": 20,
                "mouse_distance_m": 2,
                "context_switches": 1,
                "longest_focus_streak_seconds": 90,
                "focus_streak_seconds_total": 120,
                "focus_streak_samples": 1,
                "switch_recovery_seconds_total": 3,
                "switch_recovery_samples": 1,
                "longest_active_block_seconds": 300,
                "spool_backlog_batches": 1,
                "spool_backlog_bytes": 500,
                "click_hotspots": {"4:8": 5},
            },
            "dimensions": {"focus_category": "development", "window_name": "PowerShell"},
        },
    ]

    totals = db._sum_numeric_metrics(rows)
    kpis = db._kpi_signals(
        rows,
        totals,
        hours=2,
        latest_received_at=datetime(2026, 6, 7, 15, 2, tzinfo=timezone.utc),
        generated_at=datetime(2026, 6, 7, 15, 7, tzinfo=timezone.utc),
    )

    assert kpis["focus"]["context_switches_per_hour"] == 1.5
    assert kpis["focus"]["longest_focus_block_minutes"] == 3.0
    assert kpis["focus"]["avg_switch_recovery_seconds"] == 5.0
    assert kpis["typing"]["paste_share"] == 0.5
    assert kpis["typing"]["shortcut_density_per_1000_keys"] == 50.0
    assert kpis["pointer"]["scrolls_per_active_minute"] == 20.0
    assert kpis["pointer"]["hotspot_top_share"] == 0.5
    assert kpis["rhythm"]["best_hour_utc"] == 15
    assert kpis["rhythm"]["best_day"] == "2026-06-07"
    assert kpis["reliability"]["data_coverage_percent"] == 1.67
    assert kpis["reliability"]["batch_lag_minutes"] == 5.0
    assert kpis["reliability"]["spool_backlog_batches"] == 3

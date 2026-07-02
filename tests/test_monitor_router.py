import json

import hashlib
import hmac
import json
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def _client(monkeypatch, tmp_path):
    health_root = tmp_path / "health-ledger"
    agent_root = tmp_path / "agent-ledger"
    monkeypatch.setenv("VW_HEALTH_LEDGER_ROOT", str(health_root))
    monkeypatch.setenv("VW_AGENT_LEDGER_ROOT", str(agent_root))
    monkeypatch.setenv("VW_KIWI_URL", "https://localhost:5959/home")

    from app.routers.monitor import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app), health_root, agent_root


def test_monitor_overview_normalizes_health_agent_and_kiwi(monkeypatch, tmp_path):
    client, health_root, agent_root = _client(monkeypatch, tmp_path)

    _write_json(
        health_root / "data" / "rollups" / "latest.json",
        {
            "generated_at": "2026-06-04T21:57:16.910Z",
            "run_id": "20260604-175707",
            "probe_location": "Clopeux-Desktop",
            "totals": {"total": 2, "ok": 1, "failed": 1, "skipped": 0},
            "services": [
                {
                    "service_id": "vaultwares-api-local",
                    "service_name": "VaultWares API local runtime",
                    "status": "ok",
                    "paths": [{"path_id": "openapi", "duration_ms": 5, "ok": True}],
                },
                {
                    "service_id": "kiwi-local",
                    "service_name": "Kiwi local logging",
                    "status": "failed",
                    "paths": [{"path_id": "home", "duration_ms": 0, "ok": False, "failure_class": "connection"}],
                },
            ],
        },
    )
    _write_json(health_root / "data" / "alarm-state.json", {"version": 1, "incidents": {"inc-1": {"status": "active"}}})
    _write_jsonl(
        health_root / "data" / "events" / "2026" / "06" / "04.jsonl",
        [
            {"event_type": "probe_result", "service_id": "kiwi-local", "ok": False, "failure_class": "connection"},
            {"event_type": "ollama_resource_sample", "gpu_snapshot": {"available": True}},
        ],
    )
    from app.routers import monitor
    from app.routers.telemetry import agent_ledger_db

    async def fake_changes(limit=500):
        return {
            "events": [
                {
                    "source": "agent-ledger",
                    "project": "Vault Monitor",
                    "kind": "code-change",
                    "summary": "Added monitor API without leaking sensitive values",
                    "createdAt": "2026-06-06T12:00:00Z",
                    "runtime": {"model": "gpt-5.2", "mcpServers": ["VaultWares_MCP"]},
                    "commands": ["pytest tests/test_monitor_router.py"],
                }
            ]
        }

    async def fake_work_impact():
        return {
            "data": {
                "agentData": {
                    "totalEvents": 1,
                    "models": [{"name": "gpt-5.2", "count": 3}],
                    "tools": [{"name": "pytest", "count": 2}],
                    "mcpServers": [{"name": "VaultWares_MCP", "count": 4}],
                    "daySeries": [{"day": "2026-06-06", "count": 1}],
                }
            }
        }

    async def fake_input_tracker(*args, **kwargs):
        return {"source": "vaultwares-api", "status": "unavailable"}

    monkeypatch.setattr(agent_ledger_db, "get_agent_changes", fake_changes)
    monkeypatch.setattr(agent_ledger_db, "get_agent_work_impact", fake_work_impact)
    monkeypatch.setattr(monitor, "get_input_tracker", fake_input_tracker)

    response = client.get("/monitor/overview?kiwi_check=false")

    assert response.status_code == 200
    body = response.json()
    assert body["health"]["totals"]["failed"] == 1
    assert body["health"]["active_incident_count"] == 1
    assert body["agents"]["recent"][0]["project"] == "Vault Monitor"
    assert body["agents"]["usage"]["models"][0] == {"name": "gpt-5.2", "count": 3}
    assert body["logging"]["kiwi"]["status"] == "unchecked"
    assert body["input_tracker"]["status"] == "unavailable"
    assert "secret_token" not in json.dumps(body)


def test_monitor_exposes_agent_db_data_through_api(monkeypatch, tmp_path):
    client, _, agent_root = _client(monkeypatch, tmp_path)
    from app.routers.telemetry import agent_ledger_db

    async def fake_changes(limit=500):
        return {"source": "vaultwares-api", "events": [{"project": "agent-ledger", "kind": "code-change"}]}

    async def fake_work_impact():
        return {"source": "vaultwares-api", "data": {"totals": {"events": 1}}}

    monkeypatch.setattr(agent_ledger_db, "get_agent_changes", fake_changes)
    monkeypatch.setattr(agent_ledger_db, "get_agent_work_impact", fake_work_impact)

    work_impact = client.get("/monitor/work-impact")
    changes = client.get("/monitor/changes")

    assert work_impact.status_code == 200
    assert changes.status_code == 200
    assert work_impact.json()["data"]["totals"]["events"] == 1
    assert changes.json()["events"][0]["project"] == "agent-ledger"


def test_monitor_input_tracker_accepts_month_window(monkeypatch, tmp_path):
    client, _, _ = _client(monkeypatch, tmp_path)
    from app.routers import monitor

    async def fake_input_tracker(hours=24):
        return {"source": "vaultwares-api", "status": "online", "window_hours": hours}

    monkeypatch.setattr(monitor, "get_input_tracker", fake_input_tracker)

    response = client.get("/monitor/input-tracker?hours=720")

    assert response.status_code == 200
    assert response.json()["window_hours"] == 720


def test_monitor_search_filters_ledgers_case_insensitively(monkeypatch, tmp_path):
    client, health_root, agent_root = _client(monkeypatch, tmp_path)
    _write_jsonl(
        health_root / "data" / "events" / "2026" / "06" / "04.jsonl",
        [
            {
                "event_type": "probe_result",
                "timestamp": "2026-06-04T21:57:12.184Z",
                "service_id": "gateway",
                "service_name": "Gateway Probe",
                "ok": False,
                "failure_class": "tls",
            }
        ],
    )
    from app.routers.telemetry import agent_ledger_db

    async def fake_search(**kwargs):
        return {
            "items": [
                {
                    "source": "agent-ledger",
                    "project": "Vault Monitor",
                    "kind": "verification",
                    "summary": "Gateway probe correction verified",
                    "createdAt": "2026-06-06T12:00:00Z",
                    "runtime": {"model": "gpt-5.2"},
                }
            ]
        }

    monkeypatch.setattr(agent_ledger_db, "search_agent_ledger_events", fake_search)

    response = client.get("/monitor/events/search?q=GATEWAY&kind=verification&service=gateway&limit=10")

    assert response.status_code == 200
    body = response.json()
    assert [item["source"] for item in body["items"]] == ["agent-ledger", "health-ledger"]
    assert body["items"][0]["project"] == "Vault Monitor"
    assert body["items"][1]["service_id"] == "gateway"


def test_monitor_search_filters_source_and_sorts_newest_first(monkeypatch, tmp_path):
    client, health_root, _ = _client(monkeypatch, tmp_path)
    _write_jsonl(
        health_root / "data" / "events" / "2026" / "06" / "25.jsonl",
        [
            {
                "event_type": "probe_result",
                "timestamp": "2026-06-25T03:20:00Z",
                "service_id": "vaultwares-api",
                "service_name": "VaultWares API",
                "ok": True,
            }
        ],
    )
    from app.routers.telemetry import agent_ledger_db

    async def fake_search(**kwargs):
        return {
            "items": [
                {
                    "source": "agent-ledger",
                    "timestamp": "2026-06-25T03:30:00Z",
                    "project": "vault-monitor",
                    "kind": "code-change",
                    "summary": "Unified monitor shell",
                }
            ]
        }

    monkeypatch.setattr(agent_ledger_db, "search_agent_ledger_events", fake_search)

    all_response = client.get("/monitor/events/search?source=all&limit=10")
    health_response = client.get("/monitor/events/search?source=health-ledger&limit=10")

    assert [item["source"] for item in all_response.json()["items"]] == [
        "agent-ledger",
        "health-ledger",
    ]
    assert [item["source"] for item in health_response.json()["items"]] == [
        "health-ledger",
    ]


def test_monitor_services_includes_unmonitored_inventory(monkeypatch, tmp_path):
    client, health_root, _ = _client(monkeypatch, tmp_path)
    health_root.mkdir(parents=True, exist_ok=True)
    (health_root / "services.yaml").write_text(
        """
version: 1
services:
  - id: monitor
    name: Vault Monitor
    product: vaultwares
    type: site
    host: greencloud-vps
    runtime: /var/www/monitor.vaultwares.ca
    dependencies: [vaultwares-api]
    paths:
      - id: home
        path: /
  - id: postgres
    name: Shared PostgreSQL
    product: shared
    type: database
    host: vps-ovhcloud
    runtime: postgresql.service
    dependencies: []
    paths: []
""".strip(),
        encoding="utf-8",
    )
    _write_json(
        health_root / "data" / "rollups" / "latest.json",
        {
            "generated_at": "2026-06-25T03:30:00Z",
            "services": [
                {
                    "service_id": "monitor",
                    "status": "ok",
                    "paths": [{"duration_ms": 12, "ok": True}],
                }
            ],
        },
    )

    response = client.get("/monitor/services")

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 2
    assert body["items"][0] == {
        "id": "monitor",
        "name": "Vault Monitor",
        "product": "vaultwares",
        "type": "site",
        "host": "greencloud-vps",
        "runtime": "/var/www/monitor.vaultwares.ca",
        "status": "healthy",
        "checkedAt": "2026-06-25T03:30:00Z",
        "lastSuccessAt": "2026-06-25T03:30:00Z",
        "lastFailureAt": None,
        "latencyMs": 12,
        "dependencies": ["vaultwares-api"],
    }
    assert body["items"][1]["id"] == "postgres"
    assert body["items"][1]["status"] == "unmonitored"


def test_monitor_services_reads_per_service_fleet_evidence(monkeypatch, tmp_path):
    client, health_root, _ = _client(monkeypatch, tmp_path)
    health_root.mkdir(parents=True, exist_ok=True)
    (health_root / "services.yaml").write_text(
        """
version: 1
services:
  - id: api
    name: API
    product: vaultwares
    type: api
    host: vps-ovhcloud
    dependencies: [postgres]
    paths:
      - id: healthz
        path: /healthz
  - id: postgres
    name: PostgreSQL
    product: shared
    type: database
    host: vps-ovhcloud
    dependencies: []
    paths:
      - id: ready
        path: /
""".strip(),
        encoding="utf-8",
    )
    _write_json(
        health_root / "data" / "rollups" / "fleet-latest.json",
        {
            "generated_at": "2026-06-25T08:00:00Z",
            "services": [
                {
                    "service_id": "api",
                    "status": "offline",
                    "checked_at": "2026-06-25T07:59:30Z",
                    "last_success_at": "2026-06-25T07:55:00Z",
                    "last_failure_at": "2026-06-25T07:59:30Z",
                    "locations": ["greencloud-vps", "clopeux-desktop"],
                    "confirmation_count": 2,
                    "host_heartbeat": "healthy",
                    "paths": [{"duration_ms": 25, "ok": False}],
                },
                {
                    "service_id": "postgres",
                    "status": "stale",
                    "checked_at": "2026-06-25T07:00:00Z",
                    "last_success_at": "2026-06-25T07:00:00Z",
                    "locations": ["vps-ovhcloud"],
                    "confirmation_count": 0,
                    "host_heartbeat": "healthy",
                    "paths": [],
                },
            ],
        },
    )

    response = client.get("/monitor/services")

    assert response.status_code == 200
    body = response.json()
    assert [item["status"] for item in body["items"]] == ["offline", "stale"]
    assert body["items"][0]["checkedAt"] == "2026-06-25T07:59:30Z"
    assert body["items"][0]["lastSuccessAt"] == "2026-06-25T07:55:00Z"
    assert body["items"][0]["lastFailureAt"] == "2026-06-25T07:59:30Z"
    assert body["items"][0]["locations"] == ["greencloud-vps", "clopeux-desktop"]
    assert body["items"][0]["confirmationCount"] == 2
    assert body["items"][0]["hostHeartbeat"] == "healthy"
    assert all(item["status"] != "unmonitored" for item in body["items"])


def test_monitor_accepts_only_signed_location_rollups(monkeypatch, tmp_path):
    client, health_root, _ = _client(monkeypatch, tmp_path)
    monkeypatch.setenv("HEALTH_LEDGER_INGEST_SECRET", "test-ingest-secret")
    payload = {
        "probe_location_id": "greencloud-vps",
        "generated_at": "2026-06-25T08:00:00Z",
        "services": [],
    }
    body = json.dumps(payload, separators=(",", ":")).encode()
    timestamp = str(int(time.time()))
    signature = hmac.new(
        b"test-ingest-secret",
        timestamp.encode() + b"." + body,
        hashlib.sha256,
    ).hexdigest()

    rejected = client.post("/monitor/probe-rollups/greencloud-vps", content=body)
    accepted = client.post(
        "/monitor/probe-rollups/greencloud-vps",
        content=body,
        headers={
            "content-type": "application/json",
            "x-health-ledger-timestamp": timestamp,
            "x-health-ledger-signature": signature,
        },
    )

    assert rejected.status_code == 401
    assert accepted.status_code == 200
    stored = json.loads(
        (health_root / "data" / "rollups" / "locations" / "greencloud-vps.json").read_text()
    )
    assert stored["probe_location_id"] == "greencloud-vps"

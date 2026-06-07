import json

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
    _write_json(
        agent_root / "events" / "2026" / "06" / "20260606-120000-000-vault-monitor-test.json",
        {
            "project": "Vault Monitor",
            "kind": "code-change",
            "summary": "Added monitor API without leaking sensitive values",
            "createdAt": "2026-06-06T12:00:00Z",
            "runtime": {"model": "gpt-5.2", "mcpServers": ["VaultWares_MCP"]},
            "commands": ["pytest tests/test_monitor_router.py"],
            "secret_token": "do-not-render",
        },
    )
    _write_json(
        agent_root / "site" / "public" / "data" / "work-impact-data.json",
        {
            "data": {
                "agentData": {
                    "totalEvents": 1,
                    "models": [["gpt-5.2", 3], ["malformed"]],
                    "tools": [["pytest", 2]],
                    "mcpServers": [["VaultWares_MCP", 4]],
                    "daySeries": [{"day": "2026-06-06", "count": 1}],
                }
            }
        },
    )

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


def test_monitor_exposes_agent_site_data_through_api(monkeypatch, tmp_path):
    client, _, agent_root = _client(monkeypatch, tmp_path)
    _write_json(
        agent_root / "site" / "public" / "data" / "work-impact-data.json",
        {"generatedAtLocal": "2026-06-07", "data": {"totals": {"events": 1}}},
    )
    _write_json(
        agent_root / "site" / "public" / "data" / "changes-data.json",
        {"events": [{"project": "agent-ledger", "kind": "code-change"}]},
    )

    work_impact = client.get("/monitor/work-impact")
    changes = client.get("/monitor/changes")

    assert work_impact.status_code == 200
    assert changes.status_code == 200
    assert work_impact.json()["data"]["totals"]["events"] == 1
    assert changes.json()["events"][0]["project"] == "agent-ledger"


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
    _write_json(
        agent_root / "events" / "2026" / "06" / "20260606-120000-000-vault-monitor-test.json",
        {
            "project": "Vault Monitor",
            "kind": "verification",
            "summary": "Gateway probe correction verified",
            "createdAt": "2026-06-06T12:00:00Z",
            "runtime": {"model": "gpt-5.2"},
        },
    )

    response = client.get("/monitor/events/search?q=GATEWAY&kind=verification&service=gateway&limit=10")

    assert response.status_code == 200
    body = response.json()
    assert [item["source"] for item in body["items"]] == ["agent-ledger", "health-ledger"]
    assert body["items"][0]["project"] == "Vault Monitor"
    assert body["items"][1]["service_id"] == "gateway"

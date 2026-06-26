"""
V.A.U.L.T Monitor read-only API.

The browser-facing monitor consumes these normalized endpoints only. Source
ledger file formats stay behind API ingestion; browser views read normalized
DB-backed API responses.
"""
from __future__ import annotations

import json
import hashlib
import hmac
import os
import re
import sqlite3
import ssl
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.error import URLError
from urllib.request import Request, urlopen

from fastapi import APIRouter, HTTPException, Query, Request
import yaml

router = APIRouter(prefix="/monitor", tags=["monitor"])

DEFAULT_REPOS_ROOT = Path(os.environ.get("VW_REPOS_ROOT", r"C:\Users\Administrator\Desktop\Github Repos"))
DEFAULT_KIWI_URL = "https://localhost:5959/home"
DEFAULT_UPLOADS_DB = "/srv/vw-media/uploads/links.db"
DEFAULT_UPLOADS_LOG = "/srv/vw-media/uploads/upload.log"
SECRET_KEY_PARTS = ("secret", "token", "password", "credential", "apikey", "api_key", "private_key")
PROBE_LOCATIONS = {"greencloud-vps", "vps-ovhcloud", "clopeux-desktop"}

_UPLOAD_TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
_UPLOAD_FAIL_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})[.,]\d+ ERROR FAIL (?P<path>.+?): (?P<reason>.+)$"
)
_UPLOAD_RUN_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})[.,]\d+ INFO run complete: "
    r"ok=(?P<ok>\d+) fail=(?P<fail>\d+) skip=(?P<skip>\d+)$"
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _source_root(env_name: str, repo_name: str) -> Path:
    return Path(os.environ.get(env_name) or (DEFAULT_REPOS_ROOT / repo_name))


def _read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _valid_rollup_signature(body: bytes, timestamp: str, signature: str) -> bool:
    secret = os.environ.get("HEALTH_LEDGER_INGEST_SECRET", "")
    if not secret or not timestamp or not signature:
        return False
    try:
        age = abs(int(time.time()) - int(timestamp))
    except ValueError:
        return False
    if age > 300:
        return False
    expected = hmac.new(
        secret.encode("utf-8"),
        timestamp.encode("ascii") + b"." + body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(signature, expected)


@router.post("/probe-rollups/{location_id}", include_in_schema=False)
async def ingest_probe_rollup(location_id: str, request: Request) -> Dict[str, Any]:
    if location_id not in PROBE_LOCATIONS:
        raise HTTPException(status_code=404, detail="unknown probe location")
    body = await request.body()
    if len(body) > 1024 * 1024:
        raise HTTPException(status_code=413, detail="rollup too large")
    if not _valid_rollup_signature(
        body,
        request.headers.get("x-health-ledger-timestamp", ""),
        request.headers.get("x-health-ledger-signature", ""),
    ):
        raise HTTPException(status_code=401, detail="invalid rollup signature")
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="invalid rollup json") from exc
    if payload.get("probe_location_id") != location_id or not isinstance(payload.get("services"), list):
        raise HTTPException(status_code=400, detail="rollup location mismatch")
    target = _health_root() / "data" / "rollups" / "locations" / f"{location_id}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".json.tmp")
    temporary.write_bytes(body + (b"\n" if not body.endswith(b"\n") else b""))
    temporary.replace(target)
    return {"status": "accepted", "location": location_id}


def _json_files(root: Path, limit: int = 100) -> List[Path]:
    if not root.exists():
        return []
    files = [path for path in root.rglob("*.json") if path.is_file()]
    files.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return files[: max(0, limit)]


def _jsonl_files(root: Path, limit: int = 20) -> List[Path]:
    if not root.exists():
        return []
    files = [path for path in root.rglob("*.jsonl") if path.is_file()]
    files.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return files[: max(0, limit)]


def _tail_jsonl(path: Path, max_lines: int = 500) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            pos = handle.tell()
            buffer = bytearray()
            line_count = 0
            while pos > 0 and line_count < max_lines:
                step = min(8192, pos)
                pos -= step
                handle.seek(pos)
                chunk = handle.read(step)
                buffer[:0] = chunk
                line_count = buffer.count(b"\n")
            lines = bytes(buffer).splitlines()[-max_lines:]
    except Exception:
        return rows

    for line in lines:
        if not line.strip():
            continue
        try:
            parsed = json.loads(line.decode("utf-8"))
        except Exception:
            continue
        if isinstance(parsed, dict):
            rows.append(_sanitize(parsed))
    return rows


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: Dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(part in lowered for part in SECRET_KEY_PARTS):
                continue
            sanitized[key] = _sanitize(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    return value


def _contains(value: Any, needle: str) -> bool:
    if not needle:
        return True
    return needle.casefold() in json.dumps(value, ensure_ascii=False, default=str).casefold()


def _field_matches(value: Any, expected: Optional[str]) -> bool:
    if not expected:
        return True
    if value is None:
        return False
    return expected.casefold() in str(value).casefold()


def _tuple_list(value: Any, limit: int = 8) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    if not isinstance(value, list):
        return normalized
    for item in value:
        if isinstance(item, dict):
            name = item.get("name") or item.get("key") or item.get("label")
            count = item.get("count") or item.get("value") or 0
        elif isinstance(item, (list, tuple)) and item:
            name = item[0]
            count = item[1] if len(item) > 1 else 0
        else:
            continue
        try:
            parsed_count = int(count)
        except Exception:
            parsed_count = 0
        normalized.append({"name": str(name), "count": parsed_count})
    normalized.sort(key=lambda item: item["count"], reverse=True)
    return normalized[: max(0, limit)]


def _event_timestamp(event: Dict[str, Any]) -> str:
    for key in ("createdAt", "created_at", "timestamp", "time", "date"):
        value = event.get(key)
        if value:
            return str(value)
    return ""


def _health_root() -> Path:
    return _source_root("VW_HEALTH_LEDGER_ROOT", "health-ledger")


def _agent_root() -> Path:
    return _source_root("VW_AGENT_LEDGER_ROOT", "agent-ledger")


def get_health_ledger() -> Dict[str, Any]:
    root = _health_root()
    latest = _read_json(root / "data" / "rollups" / "latest.json", {}) or {}
    alarm_state = _read_json(root / "data" / "alarm-state.json", {"incidents": {}}) or {"incidents": {}}
    recent_events: List[Dict[str, Any]] = []
    for path in _jsonl_files(root / "data" / "events", limit=4):
        recent_events.extend(_tail_jsonl(path, max_lines=300))
    recent_events.sort(key=_event_timestamp, reverse=True)

    failures = [
        event
        for event in recent_events
        if event.get("event_type") == "probe_result" and event.get("ok") is False
    ][:20]
    resource_samples = [
        event for event in recent_events if event.get("event_type") == "ollama_resource_sample"
    ][:5]
    services = latest.get("services") if isinstance(latest.get("services"), list) else []
    incidents = alarm_state.get("incidents") if isinstance(alarm_state.get("incidents"), dict) else {}
    active_incidents = [
        _sanitize({"id": key, **value}) if isinstance(value, dict) else {"id": key, "value": value}
        for key, value in incidents.items()
        if not isinstance(value, dict) or str(value.get("status", "active")).casefold() not in {"closed", "resolved"}
    ]

    generated_at = latest.get("generated_at")
    return {
        "source": "health-ledger",
        "status": "ok" if latest else "missing",
        "generated_at": generated_at,
        "run_id": latest.get("run_id"),
        "probe_location": latest.get("probe_location") or latest.get("probe_location_id"),
        "totals": latest.get("totals") or {"total": 0, "ok": 0, "failed": 0, "skipped": 0},
        "services": _sanitize(services[:50]),
        "recent_failures": _sanitize(failures),
        "resource_samples": _sanitize(resource_samples),
        "active_incidents": active_incidents[:20],
        "active_incident_count": len(active_incidents),
        "notes": [
            "Probe Joker, CI Joker, gateway probe correction, Alarm Joker notifications, and sanitized incidents are source behaviors.",
            "DB-backed ingestion behind the central API is still required; file reads are transitional.",
        ],
    }


def _load_health_inventory() -> List[Dict[str, Any]]:
    path = _health_root() / "services.yaml"
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return []
    services = payload.get("services")
    return services if isinstance(services, list) else []


def _service_status(status: Optional[str], checked_at: Optional[str]) -> str:
    normalized = str(status or "").casefold()
    if not checked_at or not normalized:
        return "unmonitored"
    if normalized in {"ok", "online", "healthy"}:
        return "healthy"
    if normalized in {"failed", "offline", "error"}:
        return "offline"
    if normalized in {"stale", "missing"}:
        return "stale"
    if normalized == "unmonitored":
        return "unmonitored"
    return "degraded"


def _service_product(service_id: str) -> str:
    if service_id.startswith(
        ("prom-", "pk-", "fullxxx-", "oneporn-", "sexyprn-", "media-", "qa-", "pyload", "comet", "uploads-", "vw-drive-")
    ):
        return "prom-king"
    if service_id.startswith(("vaultwares-", "agent-ledger", "github-webhooks", "warden", "input-tracker")):
        return "vaultwares"
    return "shared"


def _service_type(service_id: str, service: Dict[str, Any]) -> str:
    if service.get("type"):
        return str(service["type"])
    if service_id.endswith("-api") or "api" in service_id:
        return "api"
    if "runner" in service_id or service_id.startswith("qa-"):
        return "runner"
    if any(token in service_id for token in ("postgres", "database", "sqlite")):
        return "database"
    runtime = str(service.get("runtime") or "").casefold()
    if "docker" in runtime or "container" in runtime:
        return "container"
    if service.get("url") and not str(service.get("url")).startswith("http://127.0.0.1"):
        return "site"
    return "service"


def get_services_summary() -> Dict[str, Any]:
    root = _health_root()
    latest = (
        _read_json(root / "data" / "rollups" / "fleet-latest.json", {})
        or _read_json(root / "data" / "rollups" / "latest.json", {})
        or {}
    )
    document_checked_at = latest.get("generated_at")
    rollup_services = latest.get("services") if isinstance(latest.get("services"), list) else []
    by_id = {
        str(item.get("service_id")): item
        for item in rollup_services
        if isinstance(item, dict) and item.get("service_id")
    }
    items: List[Dict[str, Any]] = []

    for service in _load_health_inventory():
        if not isinstance(service, dict) or not service.get("id"):
            continue
        service_id = str(service["id"])
        rollup = by_id.get(service_id)
        checked_at = (
            rollup.get("checked_at") if isinstance(rollup, dict) else None
        ) or document_checked_at
        paths = rollup.get("paths") if isinstance(rollup, dict) and isinstance(rollup.get("paths"), list) else []
        latencies = [
            int(path["duration_ms"])
            for path in paths
            if isinstance(path, dict) and isinstance(path.get("duration_ms"), (int, float))
        ]
        status = _service_status(rollup.get("status") if rollup else None, checked_at if rollup else None)
        item = {
                "id": service_id,
                "name": service.get("name") or service_id,
                "product": service.get("product") or (rollup or {}).get("product") or _service_product(service_id),
                "type": service.get("type") or (rollup or {}).get("type") or _service_type(service_id, service),
                "host": service.get("host") or (rollup or {}).get("host") or (service.get("probe_locations") or ["unknown"])[0],
                "runtime": service.get("runtime") or (rollup or {}).get("runtime"),
                "status": status,
                "checkedAt": checked_at if rollup else None,
                "lastSuccessAt": (
                    rollup.get("last_success_at") if isinstance(rollup, dict) else None
                ) or (checked_at if status == "healthy" else None),
                "lastFailureAt": (
                    rollup.get("last_failure_at") if isinstance(rollup, dict) else None
                ) or (checked_at if status in {"degraded", "offline"} else None),
                "latencyMs": max(latencies) if latencies else None,
                "dependencies": (
                    service.get("dependencies")
                    if isinstance(service.get("dependencies"), list)
                    else (rollup or {}).get("dependencies") or []
                ),
            }
        if isinstance(rollup, dict) and "locations" in rollup:
            item["locations"] = rollup.get("locations") or []
            item["confirmationCount"] = int(rollup.get("confirmation_count") or 0)
            item["hostHeartbeat"] = rollup.get("host_heartbeat") or "unknown"
            if rollup.get("expected_state"):
                item["expectedState"] = rollup["expected_state"]
        items.append(item)

    return {
        "source": "health-ledger",
        "generatedAt": _utc_now(),
        "count": len(items),
        "items": _sanitize(items),
    }


def _load_work_impact(root: Path) -> Dict[str, Any]:
    candidates = [
        root / "site" / "public" / "data" / "work-impact-data.json",
        root / "work-impact.state.json",
    ]
    for path in candidates:
        payload = _read_json(path, {})
        if payload:
            return payload
    return {}


def _load_changes(root: Path) -> Dict[str, Any]:
    payload = _read_json(root / "site" / "public" / "data" / "changes-data.json", {})
    if payload:
        return payload
    events: List[Dict[str, Any]] = []
    for path in _json_files(root / "events", limit=120):
        event = _read_json(path, {})
        if isinstance(event, dict):
            events.append(_agent_event_summary(event, path))
    events.sort(key=lambda item: item.get("timestamp") or item.get("id") or "", reverse=True)
    return {"events": events}


async def get_input_tracker(hours: int = 24) -> Dict[str, Any]:
    try:
        from app.routers.telemetry.db import get_input_summary

        return await get_input_summary(hours=hours)
    except Exception:
        return {
            "source": "vaultwares-api",
            "status": "unavailable",
            "generated_at": _utc_now(),
            "latest_received_at": None,
            "window_hours": hours,
            "totals": {},
            "derived": {"wpm": 0, "cpm": 0, "correction_ratio": 0, "click_to_travel_ratio": 0},
            "key_latency_buckets": [],
            "click_hotspots": [],
            "focus_categories": [],
            "focus_windows": [],
            "kpis": {
                "focus": {},
                "typing": {},
                "pointer": {},
                "rhythm": {},
                "reliability": {},
            },
            "events": [],
            "privacy": {
                "raw_text": False,
                "clipboard_contents": False,
                "window_titles": "hashed_or_redacted",
            },
            "message": "Input telemetry summary unavailable; check pipelines telemetry DB configuration.",
        }


def _agent_event_summary(event: Dict[str, Any], path: Path) -> Dict[str, Any]:
    runtime = event.get("runtime") if isinstance(event.get("runtime"), dict) else {}
    return _sanitize(
        {
            "source": "agent-ledger",
            "id": event.get("id") or path.stem,
            "timestamp": _event_timestamp(event),
            "project": event.get("project") or event.get("repo") or "General Tasks",
            "kind": event.get("kind") or event.get("type") or "general",
            "summary": event.get("summary") or event.get("title") or "",
            "commands": event.get("commands") or [],
            "files": event.get("files") or [],
            "model": runtime.get("model") or event.get("model"),
            "tool": runtime.get("tool") or event.get("tool"),
            "mcp_servers": runtime.get("mcpServers") or runtime.get("mcp_servers") or event.get("mcpServers") or [],
        }
    )


async def get_agent_ledger() -> Dict[str, Any]:
    try:
        from app.routers.telemetry.agent_ledger_db import get_agent_changes, get_agent_work_impact

        changes_payload = await get_agent_changes(limit=80)
        work_impact = await get_agent_work_impact()
    except Exception as exc:
        return {
            "source": "vaultwares-api",
            "status": "unavailable",
            "recent": [],
            "usage": {"total_events": 0, "models": [], "tools": [], "mcp_servers": [], "day_series": []},
            "message": f"Agent ledger DB summary unavailable: {exc}",
        }

    recent = changes_payload.get("events") if isinstance(changes_payload.get("events"), list) else []
    data = work_impact.get("data") if isinstance(work_impact.get("data"), dict) else {}
    agent_data = data.get("agentData") if isinstance(data.get("agentData"), dict) else {}
    return {
        "source": "vaultwares-api",
        "status": "ok" if recent or agent_data else "empty",
        "recent": recent[:40],
        "usage": {
            "total_events": agent_data.get("totalEvents") or len(recent),
            "models": _tuple_list(agent_data.get("models")),
            "tools": _tuple_list(agent_data.get("tools")),
            "mcp_servers": _tuple_list(agent_data.get("mcpServers") or agent_data.get("mcp_servers")),
            "day_series": _sanitize(agent_data.get("daySeries") or [])[-21:],
        },
        "notes": [
            "Agent ledger aggregates are read from Postgres behind vaultwares-api.",
        ],
    }


def get_kiwi_status(check: bool = True) -> Dict[str, Any]:
    url = os.environ.get("VW_KIWI_URL", DEFAULT_KIWI_URL)
    if not check:
        return {
            "source": "kiwi",
            "status": "unchecked",
            "url": url,
            "checked_at": None,
            "message": "Reachability check skipped for this request.",
        }
    started = time.perf_counter()
    request = Request(url, headers={"User-Agent": "vault-monitor/0.1"})
    try:
        context = ssl._create_unverified_context()
        with urlopen(request, timeout=2.5, context=context) as response:
            elapsed_ms = round((time.perf_counter() - started) * 1000)
            return {
                "source": "kiwi",
                "status": "online",
                "url": url,
                "checked_at": _utc_now(),
                "status_code": response.getcode(),
                "duration_ms": elapsed_ms,
                "message": "Kiwi home responded.",
            }
    except (OSError, URLError, TimeoutError) as exc:
        elapsed_ms = round((time.perf_counter() - started) * 1000)
        return {
            "source": "kiwi",
            "status": "offline",
            "url": url,
            "checked_at": _utc_now(),
            "duration_ms": elapsed_ms,
            "message": str(exc),
        }


def _uploads_db_path() -> Path:
    return Path(os.environ.get("VW_UPLOADS_DB") or DEFAULT_UPLOADS_DB)


def _uploads_log_path() -> Path:
    return Path(os.environ.get("VW_UPLOADS_LOG") or DEFAULT_UPLOADS_LOG)


def _tail_text(path: Path, max_bytes: int = 256 * 1024) -> List[str]:
    if not path.exists():
        return []
    try:
        size = path.stat().st_size
        with path.open("rb") as handle:
            if size > max_bytes:
                handle.seek(-max_bytes, os.SEEK_END)
            chunk = handle.read()
    except Exception:
        return []
    return chunk.decode("utf-8", errors="replace").splitlines()


def _uploads_db_rows(limit: int) -> List[Dict[str, Any]]:
    db = _uploads_db_path()
    if not db.exists():
        return []
    try:
        with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                "SELECT id, local_path, remote_path, drive_link, size_bytes, media_type, "
                "uploaded_at, unmonitored, linkvertise_link, linkvertise_id "
                "FROM uploads ORDER BY id DESC LIMIT ?",
                (limit,),
            )
            return [dict(row) for row in cur.fetchall()]
    except Exception:
        return []


def _uploads_db_ok_count() -> Optional[int]:
    db = _uploads_db_path()
    if not db.exists():
        return None
    try:
        with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as conn:
            cur = conn.execute("SELECT COUNT(*) FROM uploads")
            row = cur.fetchone()
            return int(row[0]) if row else 0
    except Exception:
        return None


def _parse_uploads_log(limit_failures: int, limit_runs: int) -> Dict[str, Any]:
    lines = _tail_text(_uploads_log_path())
    failures: List[Dict[str, Any]] = []
    runs: List[Dict[str, Any]] = []
    other_errors: List[Dict[str, Any]] = []
    for line in lines:
        m_fail = _UPLOAD_FAIL_RE.match(line)
        if m_fail:
            failures.append(
                {
                    "timestamp": m_fail.group("ts"),
                    "path": m_fail.group("path"),
                    "reason": m_fail.group("reason"),
                }
            )
            continue
        m_run = _UPLOAD_RUN_RE.match(line)
        if m_run:
            runs.append(
                {
                    "timestamp": m_run.group("ts"),
                    "ok": int(m_run.group("ok")),
                    "fail": int(m_run.group("fail")),
                    "skip": int(m_run.group("skip")),
                }
            )
            continue
        if " ERROR " in line:
            ts_match = _UPLOAD_TS_RE.match(line)
            other_errors.append(
                {
                    "timestamp": ts_match.group(1) if ts_match else None,
                    "message": line.split(" ERROR ", 1)[1],
                }
            )
    return {
        "failures": list(reversed(failures))[:limit_failures],
        "runs": list(reversed(runs))[:limit_runs],
        "other_errors": list(reversed(other_errors))[:25],
    }


def _uploads_log_run_totals() -> Dict[str, int]:
    totals = {"ok": 0, "fail": 0, "skip": 0, "runs": 0}
    log_path = _uploads_log_path()
    if not log_path.exists():
        return totals
    try:
        with log_path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                match = _UPLOAD_RUN_RE.match(line)
                if not match:
                    continue
                totals["ok"] += int(match.group("ok"))
                totals["fail"] += int(match.group("fail"))
                totals["skip"] += int(match.group("skip"))
                totals["runs"] += 1
    except Exception:
        return {"ok": 0, "fail": 0, "skip": 0, "runs": 0}
    return totals


def get_uploads_summary(limit_recent: int = 30, limit_failures: int = 25) -> Dict[str, Any]:
    db_path = _uploads_db_path()
    log_path = _uploads_log_path()
    log_data = _parse_uploads_log(limit_failures=limit_failures, limit_runs=60)
    recent_uploads = _uploads_db_rows(limit_recent)

    window_start = datetime.now(timezone.utc).timestamp() - 24 * 3600
    totals = {"ok": 0, "fail": 0, "skip": 0, "runs": 0}
    for run in log_data["runs"]:
        try:
            ts = (
                datetime.strptime(run["timestamp"], "%Y-%m-%d %H:%M:%S")
                .replace(tzinfo=timezone.utc)
                .timestamp()
            )
        except Exception:
            continue
        if ts < window_start:
            continue
        totals["ok"] += run["ok"]
        totals["fail"] += run["fail"]
        totals["skip"] += run["skip"]
        totals["runs"] += 1

    overall_totals = _uploads_log_run_totals()
    overall_ok = _uploads_db_ok_count()
    if overall_ok is not None:
        overall_totals["ok"] = overall_ok

    if not db_path.exists() and not log_path.exists():
        status = "missing"
    elif log_data["failures"]:
        try:
            last_fail = (
                datetime.strptime(log_data["failures"][0]["timestamp"], "%Y-%m-%d %H:%M:%S")
                .replace(tzinfo=timezone.utc)
                .timestamp()
            )
            status = "failed" if last_fail >= window_start else "ok"
        except Exception:
            status = "ok"
    else:
        status = "ok"

    return {
        "source": "vw-drive-upload",
        "status": status,
        "generated_at": _utc_now(),
        "paths": {"db": str(db_path), "log": str(log_path)},
        "totals_24h": totals,
        "totals_overall": overall_totals,
        "recent_failures": log_data["failures"],
        "recent_runs": log_data["runs"][:15],
        "other_errors": log_data["other_errors"],
        "recent_uploads": recent_uploads,
    }


@router.get("/health-ledger")
def health_ledger() -> Dict[str, Any]:
    return get_health_ledger()


@router.get("/services")
def services() -> Dict[str, Any]:
    return get_services_summary()


@router.get("/agent-ledger")
async def agent_ledger() -> Dict[str, Any]:
    return await get_agent_ledger()


@router.get("/work-impact")
async def work_impact() -> Dict[str, Any]:
    from app.routers.telemetry.agent_ledger_db import get_agent_work_impact

    return _sanitize(await get_agent_work_impact())


@router.get("/changes")
async def changes(limit: int = Query(500, ge=1, le=2000)) -> Dict[str, Any]:
    from app.routers.telemetry.agent_ledger_db import get_agent_changes

    return _sanitize(await get_agent_changes(limit=limit))


@router.get("/logging/kiwi")
def logging_kiwi(check: bool = Query(True)) -> Dict[str, Any]:
    return {"kiwi": get_kiwi_status(check=check)}


@router.get("/input-tracker")
async def input_tracker(hours: int = Query(24, ge=1, le=24 * 14)) -> Dict[str, Any]:
    return await get_input_tracker(hours=hours)


@router.get("/uploads")
def uploads(
    limit_recent: int = Query(30, ge=1, le=200),
    limit_failures: int = Query(25, ge=1, le=200),
) -> Dict[str, Any]:
    return get_uploads_summary(limit_recent=limit_recent, limit_failures=limit_failures)


@router.get("/overview")
async def overview(
    kiwi_check: bool = Query(False),
    hours: int = Query(24, ge=1, le=24 * 14),
) -> Dict[str, Any]:
    health = get_health_ledger()
    agents = await get_agent_ledger()
    logging = {"kiwi": get_kiwi_status(check=kiwi_check)}
    input_tracker = await get_input_tracker(hours=hours)
    uploads_summary = get_uploads_summary(limit_recent=10, limit_failures=10)
    return {
        "name": "V.A.U.L.T Monitor",
        "internal_name": "Vault Authenticated Unified Ledger Telemetry Monitor",
        "generated_at": _utc_now(),
        "health": health,
        "agents": agents,
        "logging": logging,
        "input_tracker": input_tracker,
        "uploads": uploads_summary,
        "api_owner": "vaultwares-api",
        "storage_note": (
            "agent-ledger and input tracker summaries are DB-backed behind vaultwares-api; "
            "health-ledger and Kiwi richer summaries still need durable ingestion."
        ),
    }


def _health_search_items(filters: Dict[str, Optional[str]], query: str, limit: int) -> List[Dict[str, Any]]:
    root = _health_root()
    items: List[Dict[str, Any]] = []
    for path in _jsonl_files(root / "data" / "events", limit=12):
        for event in _tail_jsonl(path, max_lines=800):
            if not _contains(event, query):
                continue
            if not _field_matches(event.get("service_id") or event.get("service_name"), filters.get("service")):
                continue
            if not _field_matches(event.get("run_id"), filters.get("run")):
                continue
            if not _field_matches(event.get("event_type"), filters.get("event")):
                continue
            if not _field_matches(event.get("timestamp"), filters.get("date")):
                continue
            ok_filter = filters.get("ok")
            if ok_filter and str(event.get("ok")).casefold() != ok_filter.casefold():
                continue
            items.append(
                _sanitize(
                    {
                        "source": "health-ledger",
                        "timestamp": event.get("timestamp"),
                        "event_type": event.get("event_type"),
                        "run_id": event.get("run_id"),
                        "service_id": event.get("service_id"),
                        "service_name": event.get("service_name"),
                        "ok": event.get("ok"),
                        "failure_class": event.get("failure_class"),
                        "status_code": event.get("status_code"),
                        "duration_ms": event.get("duration_ms"),
                    }
                )
            )
            if len(items) >= limit:
                return items
    return items


def _agent_search_items(filters: Dict[str, Optional[str]], query: str, limit: int) -> List[Dict[str, Any]]:
    root = _agent_root()
    items: List[Dict[str, Any]] = []
    for path in _json_files(root / "events", limit=160):
        event = _read_json(path, {})
        if not isinstance(event, dict) or not _contains(event, query):
            continue
        runtime = event.get("runtime") if isinstance(event.get("runtime"), dict) else {}
        if not _field_matches(event.get("project") or event.get("repo"), filters.get("project")):
            continue
        if not _field_matches(event.get("kind") or event.get("type"), filters.get("kind")):
            continue
        if not _field_matches(runtime.get("model") or event.get("model"), filters.get("model")):
            continue
        if not _field_matches(runtime.get("tool") or event.get("tool"), filters.get("tool")):
            continue
        servers = runtime.get("mcpServers") or runtime.get("mcp_servers") or event.get("mcpServers") or []
        if not _field_matches(" ".join(str(server) for server in servers), filters.get("mcp_server")):
            continue
        if not _field_matches(_event_timestamp(event), filters.get("date")):
            continue
        items.append(_agent_event_summary(event, path))
        if len(items) >= limit:
            return items
    return items


@router.get("/events/search")
async def events_search(
    q: str = "",
    source: str = Query("all", pattern="^(all|agent-ledger|health-ledger)$"),
    project: Optional[str] = None,
    kind: Optional[str] = None,
    model: Optional[str] = None,
    tool: Optional[str] = None,
    mcp_server: Optional[str] = None,
    service: Optional[str] = None,
    run: Optional[str] = None,
    event: Optional[str] = None,
    date: Optional[str] = None,
    ok: Optional[str] = None,
    limit: int = Query(40, ge=1, le=100),
) -> Dict[str, Any]:
    filters = {
        "project": project,
        "kind": kind,
        "model": model,
        "tool": tool,
        "mcp_server": mcp_server,
        "service": service,
        "run": run,
        "event": event,
        "date": date,
        "ok": ok,
    }
    from app.routers.telemetry.agent_ledger_db import search_agent_ledger_events

    agent_items: List[Dict[str, Any]] = []
    health_items: List[Dict[str, Any]] = []
    if source in {"all", "agent-ledger"}:
        agent_result = await search_agent_ledger_events(
            q=q,
            project=project,
            kind=kind,
            model=model,
            tool=tool,
            mcp_server=mcp_server,
            date=date,
            limit=limit,
        )
        raw_items = agent_result.get("items") if isinstance(agent_result.get("items"), list) else []
        agent_items = [
            {
                **item,
                "source": "agent-ledger",
                "timestamp": item.get("timestamp") or item.get("createdAt") or item.get("created_at"),
            }
            for item in raw_items
            if isinstance(item, dict)
        ]
    if source in {"all", "health-ledger"}:
        health_items = _health_search_items(filters, q, limit)
    items = sorted(
        agent_items + health_items,
        key=lambda item: str(item.get("timestamp") or ""),
        reverse=True,
    )[:limit]
    return {
        "query": q,
        "source": source,
        "filters": {key: value for key, value in filters.items() if value},
        "count": len(items),
        "items": items,
        "notes": [
            "Filters follow the LEDGER_LOOKUP/MCP semantics conceptually: project, kind, model, service, run, event, date, and case-insensitive search.",
            "Agent ledger search is DB-backed; health-ledger search still uses bounded JSONL reads until health ingestion lands.",
        ],
    }

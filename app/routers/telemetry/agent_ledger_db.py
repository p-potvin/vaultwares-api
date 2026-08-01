from __future__ import annotations

from db import ProjectCommit

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .db import get_pool

_ROOT = Path(__file__).resolve().parents[3]
_SCHEMA_SQL = _ROOT / "migrations" / "telemetry" / "002_agent_ledger.sql"
_schema_ready = False

SECRET_KEY_PARTS = ("secret", "token", "password", "credential", "apikey", "api_key", "private_key")


async def ensure_agent_ledger_schema() -> None:
    global _schema_ready
    if _schema_ready:
        return
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(_SCHEMA_SQL.read_text(encoding="utf-8"))
    _schema_ready = True


def _json(value: Any, default: Any) -> str:
    return json.dumps(value if value is not None else default, ensure_ascii=False, separators=(",", ":"), default=str)


def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _as_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []
    return []


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(part in lowered for part in SECRET_KEY_PARTS):
                continue
            out[key] = _sanitize(item)
        return out
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    return value


def _parse_timestamp(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    if "." in text:
        head, tail = text.split(".", 1)
        offset = ""
        for marker in ("+", "-"):
            idx = tail.find(marker)
            if idx > 0:
                offset = tail[idx:]
                tail = tail[:idx]
                break
        text = f"{head}.{tail[:6]}{offset}"
    try:
        parsed = datetime.fromisoformat(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _event_timestamp(event: Dict[str, Any]) -> str:
    for key in ("createdAt", "created_at", "timestamp", "time", "date"):
        value = event.get(key)
        if value:
            return str(value)
    return ""


def _raw_to_change_event(raw: Dict[str, Any]) -> Dict[str, Any]:
    return _sanitize(
        {
            "source": "agent-ledger",
            "id": raw.get("id"),
            "createdAt": raw.get("createdAt") or raw.get("created_at") or raw.get("timestamp"),
            "createdAtLocal": raw.get("createdAtLocal") or raw.get("created_at_local"),
            "project": raw.get("project") or raw.get("repo") or "General Tasks",
            "kind": raw.get("kind") or raw.get("type") or "general",
            "summary": raw.get("summary") or raw.get("title") or "",
            "actor": raw.get("actor"),
            "agentHeader": raw.get("agentHeader") or raw.get("agent_header"),
            "commands": raw.get("commands") or [],
            "files": raw.get("files") or [],
            "planPath": raw.get("planPath") or raw.get("plan_path"),
            "git": raw.get("git"),
            "runtime": raw.get("runtime") or {},
            "telemetry": raw.get("telemetry") or {},
        }
    )


def _kind_parts(kind: str) -> List[str]:
    return [part.strip() for part in str(kind or "general").replace("|", ",").replace("+", ",").split(",") if part.strip()]


async def store_agent_ledger_events(events: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    if os.environ.get("VW_TELEMETRY_AUTO_SCHEMA", "1") == "1":
        await ensure_agent_ledger_schema()
    pool = await get_pool()
    inserted = 0
    duplicates = 0
    received = 0
    async with pool.acquire() as conn:
        async with conn.transaction():
            for event in events:
                received += 1
                event_id = str(event.get("id") or "").strip()
                if not event_id:
                    continue
                result = await conn.execute(
                    """
                    INSERT INTO agent_ledger_events
                      (id, content_hash, created_at, created_at_local, timezone, project, kind, actor, summary,
                       commands, files, runtime, telemetry, git, plan_path, workspace_root, cwd, source_path, raw)
                    VALUES
                      ($1, $2, $3, $4, $5, $6, $7, $8, $9,
                       $10::jsonb, $11::jsonb, $12::jsonb, $13::jsonb, $14::jsonb, $15, $16, $17, $18, $19::jsonb)
                    ON CONFLICT DO NOTHING
                    """,
                    event_id,
                    event.get("contentHash") or event.get("content_hash"),
                    _parse_timestamp(_event_timestamp(event)),
                    event.get("createdAtLocal") or event.get("created_at_local"),
                    event.get("timezone"),
                    event.get("project") or event.get("repo") or "General Tasks",
                    event.get("kind") or event.get("type") or "general",
                    event.get("actor"),
                    event.get("summary") or event.get("title") or "",
                    _json(event.get("commands"), []),
                    _json(event.get("files"), []),
                    _json(event.get("runtime"), {}),
                    _json(event.get("telemetry"), {}),
                    _json(event.get("git"), None) if event.get("git") is not None else None,
                    event.get("planPath") or event.get("plan_path"),
                    event.get("workspaceRoot") or event.get("workspace_root"),
                    event.get("cwd"),
                    event.get("sourcePath") or event.get("source_path"),
                    _json(event, {}),
                )
                if result.endswith("1"):
                    inserted += 1
                else:
                    duplicates += 1
    return {"received": received, "inserted": inserted, "duplicates": duplicates}


async def get_agent_changes(limit: int = 500) -> Dict[str, Any]:
    if os.environ.get("VW_TELEMETRY_AUTO_SCHEMA", "1") == "1":
        await ensure_agent_ledger_schema()
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT raw
            FROM agent_ledger_events
            ORDER BY COALESCE(created_at, ingested_at) DESC, id DESC
            LIMIT $1
            """,
            max(1, min(limit, 2000)),
        )
    events = [_raw_to_change_event(_as_dict(row["raw"])) for row in rows]
    return {
        "source": "vaultwares-api",
        "status": "ok" if events else "empty",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "events": events,
    }


async def search_agent_ledger_events(
    q: str = "",
    project: Optional[str] = None,
    kind: Optional[str] = None,
    model: Optional[str] = None,
    tool: Optional[str] = None,
    mcp_server: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 100,
) -> Dict[str, Any]:
    if os.environ.get("VW_TELEMETRY_AUTO_SCHEMA", "1") == "1":
        await ensure_agent_ledger_schema()
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT raw
            FROM agent_ledger_events
            WHERE ($1::text = '' OR (
                (raw->>'summary' ILIKE '%' || $1 || '%') OR
                (raw->>'kind' ILIKE '%' || $1 || '%') OR
                (raw->>'actor' ILIKE '%' || $1 || '%') OR
                (raw->>'agentHeader' ILIKE '%' || $1 || '%') OR
                (raw->>'agent_header' ILIKE '%' || $1 || '%') OR
                (raw->>'plan' ILIKE '%' || $1 || '%') OR
                (raw->>'planPath' ILIKE '%' || $1 || '%') OR
                (raw->>'plan_path' ILIKE '%' || $1 || '%') OR
                (raw->'commands')::text ILIKE '%' || $1 || '%' OR
                (raw->'files')::text ILIKE '%' || $1 || '%' OR
                (raw->'runtime')::text ILIKE '%' || $1 || '%'
              ))
              AND ($2::text IS NULL OR project ILIKE '%' || $2 || '%')
              AND ($3::text IS NULL OR kind ILIKE '%' || $3 || '%')
              AND ($4::text IS NULL OR runtime::text ILIKE '%' || $4 || '%')
              AND ($5::text IS NULL OR runtime::text ILIKE '%' || $5 || '%')
              AND ($6::text IS NULL OR runtime::text ILIKE '%' || $6 || '%')
              AND ($7::text IS NULL OR created_at::date >= $7::date)
              AND ($8::text IS NULL OR created_at::date <= $8::date)
            ORDER BY COALESCE(created_at, ingested_at) DESC, id DESC
            LIMIT $9
            """,
            q,
            project,
            kind,
            model,
            tool,
            mcp_server,
            start_date,
            end_date,
            max(1, min(limit, 500)),
        )
    items = [_raw_to_change_event(_as_dict(row["raw"])) for row in rows]
    return {"query": q, "count": len(items), "items": items}


async def get_agent_work_impact() -> Dict[str, Any]:
    if os.environ.get("VW_TELEMETRY_AUTO_SCHEMA", "1") == "1":
        await ensure_agent_ledger_schema()
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, created_at, project, kind, actor, runtime, raw
            FROM agent_ledger_events
            ORDER BY COALESCE(created_at, ingested_at) ASC, id ASC
            """
        )

    days: Dict[str, Dict[str, Any]] = {}
    months: Dict[str, int] = {}
    kinds: Dict[str, int] = {}
    projects: Dict[str, Dict[str, Any]] = {}
    hours = {hour: 0 for hour in range(24)}
    dows = {label: 0 for label in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]}
    actors: Dict[str, int] = {}
    models: Dict[str, int] = {}
    tools: Dict[str, int] = {}
    mcp_servers: Dict[str, int] = {}
    agent_day_series: Dict[str, int] = {}
    min_created: Optional[datetime] = None
    max_created: Optional[datetime] = None

    for row in rows:
        created_utc = row["created_at"]
        if not created_utc:
            continue
        if created_utc.tzinfo is None:
            created_utc = created_utc.replace(tzinfo=timezone.utc)
            
        min_created = created_utc if min_created is None or created_utc < min_created else min_created
        max_created = created_utc if max_created is None or created_utc > max_created else max_created
        
        raw = _as_dict(row["raw"])
        
        # Determine local time for bucketing (day, hour, dow)
        created_local = created_utc
        local_str = raw.get("createdAtLocal") or raw.get("created_at_local")
        if local_str:
            try:
                # "2026-06-21 21:25" or similar ISO-ish format
                created_local = datetime.fromisoformat(str(local_str).strip())
            except Exception:
                pass
                
        day = created_local.date().isoformat()
        month = day[:7]
        project = row["project"] or "General Tasks"
        kind = row["kind"] or "general"
        actor = row["actor"] or "AI Agent"
        runtime = _as_dict(row["runtime"])

        day_row = days.setdefault(day, {"day": day, "entries": 0, "projects": set(), "kinds": {}})
        day_row["entries"] += 1
        day_row["projects"].add(project)
        for part in _kind_parts(kind):
            day_row["kinds"][part] = day_row["kinds"].get(part, 0) + 1
            kinds[part] = kinds.get(part, 0) + 1

        months[month] = months.get(month, 0) + 1
        hours[created_local.hour] += 1
        dows[created_local.strftime("%a")] += 1
        actors[actor] = actors.get(actor, 0) + 1
        agent_day_series[day] = agent_day_series.get(day, 0) + 1

        project_row = projects.setdefault(
            project,
            {"project": project, "entries": 0, "firstDay": day, "lastDay": day, "kinds": {}, "recent": []},
        )
        project_row["entries"] += 1
        project_row["firstDay"] = min(project_row["firstDay"], day)
        project_row["lastDay"] = max(project_row["lastDay"], day)
        for part in _kind_parts(kind):
            project_row["kinds"][part] = project_row["kinds"].get(part, 0) + 1
        summary = raw.get("summary") or ""
        if summary and len(project_row["recent"]) < 5:
            project_row["recent"].append(summary)

        model = runtime.get("model") or raw.get("model")
        if model:
            models[str(model)] = models.get(str(model), 0) + 1
        for tool in _as_list(runtime.get("toolsUsed") or runtime.get("tools_used") or raw.get("toolsUsed")):
            tools[str(tool)] = tools.get(str(tool), 0) + 1
        for server in _as_list(runtime.get("mcpServersAccessed") or runtime.get("mcp_servers_accessed") or raw.get("mcpServers")):
            mcp_servers[str(server)] = mcp_servers.get(str(server), 0) + 1

    day_series = []
    for day, row in sorted(days.items()):
        day_series.append(
            {
                "day": day,
                "entries": row["entries"],
                "count": row["entries"],
                "projects": sorted(row["projects"]),
                "kinds": row["kinds"],
            }
        )

    project_series = sorted(projects.values(), key=lambda item: (-item["entries"], item["project"].casefold()))
    month_series = [{"month": month, "count": count} for month, count in sorted(months.items())]
    kind_series = [{"kind": key, "count": value} for key, value in sorted(kinds.items(), key=lambda item: (-item[1], item[0].casefold()))]
    hour_series = [{"hour": hour, "count": count} for hour, count in hours.items()]
    dow_series = [{"label": label, "count": dows[label]} for label in dows]
    total_events = len(rows)

    commit_samples = []
    try:
        commits = await ProjectCommit.all().prefetch_related("project").order_by("-date").limit(10000)
        for c in commits:
            commit_samples.append({
                "project": c.project_id,
                "commit": c.hash,
                "day": c.date.strftime("%Y-%m-%d"),
                "message": c.message,
                "author": c.author,
                "insertions": c.raw_insertions,
                "deletions": c.raw_deletions,
                "filesTouched": c.files_changed,
                "cleanChurnLines": c.clean_insertions + c.clean_deletions,
                "filesClean": c.files_changed
            })
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Failed to fetch commit samples: {e}")

    data = {
        "_minCreatedAtUtc": min_created.isoformat().replace("+00:00", "Z") if min_created else None,
        "generatedAtLocal": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "range": {
            "start": min_created.date().isoformat() if min_created else None,
            "end": max_created.date().isoformat() if max_created else None,
        },
        "totals": {"events": total_events, "activeDays": len(days), "projects": len(projects)},
        "series": {"days": day_series, "months": month_series, "kinds": kind_series, "projects": project_series},
        "commitSamples": commit_samples,
        "hourSeries": hour_series,
        "dowSeries": dow_series,
        "agentData": {
            "totalEvents": total_events,
            "models": [{"name": key, "count": value} for key, value in sorted(models.items(), key=lambda item: (-item[1], item[0].casefold()))],
            "actors": [{"name": key, "count": value} for key, value in sorted(actors.items(), key=lambda item: (-item[1], item[0].casefold()))],
            "tools": [{"name": key, "count": value} for key, value in sorted(tools.items(), key=lambda item: (-item[1], item[0].casefold()))],
            "mcpServers": [{"name": key, "count": value} for key, value in sorted(mcp_servers.items(), key=lambda item: (-item[1], item[0].casefold()))],
            "daySeries": [{"day": day, "count": count} for day, count in sorted(agent_day_series.items())],
        },
    }
    return {
        "source": "vaultwares-api",
        "status": "ok" if rows else "empty",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "config": {"startDate": "2026-03-11", "primaryCommitMetric": "ledgerEvents", "storage": "postgres"},
        "data": data,
    }

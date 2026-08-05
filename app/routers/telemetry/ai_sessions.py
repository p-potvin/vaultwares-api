"""AI assistant session telemetry: ingest + the read endpoints vault-monitor uses.

Ingest mirrors the input-telemetry contract (x-api-key, batch POST). The read
endpoints are unauthenticated like the other telemetry summaries so the
monitor dashboard can poll them directly.
"""

from __future__ import annotations

import os
import secrets
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .ai_sessions_db import (
    get_projects,
    get_summary,
    get_timeline,
    search_sessions,
    store_session_batch,
)

router = APIRouter(prefix="/api/telemetry/ai-sessions", tags=["telemetry-ai-sessions"])


class AiSession(BaseModel):
    # Collectors gain fields over time; unknown ones are folded into `extra`
    # by the persistence layer rather than rejected here.
    model_config = ConfigDict(extra="allow", protected_namespaces=())

    tool: str = Field(min_length=1, max_length=64)
    session_id: str = Field(min_length=1, max_length=200)
    host: Optional[str] = Field(default=None, max_length=120)
    title: Optional[str] = None
    project: Optional[str] = Field(default=None, max_length=200)
    cwd: Optional[str] = None
    model: Optional[str] = Field(default=None, max_length=120)
    started_at: Optional[datetime] = None
    last_activity_at: Optional[datetime] = None
    message_count: Optional[int] = Field(default=None, ge=0)
    user_message_count: Optional[int] = Field(default=None, ge=0)
    tokens_used: Optional[int] = Field(default=None, ge=0)
    input_tokens: Optional[int] = Field(default=None, ge=0)
    output_tokens: Optional[int] = Field(default=None, ge=0)
    cached_input_tokens: Optional[int] = Field(default=None, ge=0)
    reasoning_tokens: Optional[int] = Field(default=None, ge=0)
    archived: Optional[bool] = None
    git_branch: Optional[str] = Field(default=None, max_length=200)
    source_path: Optional[str] = None
    size_bytes: Optional[int] = Field(default=None, ge=0)
    parser: str = Field(default="full", max_length=32)


class AiSessionBatch(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    schema_version: int = Field(default=1, ge=1, le=5, alias="schema")
    source: str = Field(default="vw-ai-sessions", min_length=1, max_length=80)
    host: str = Field(min_length=1, max_length=120)
    collected_at: Optional[datetime] = Field(default=None, alias="collectedAt")
    batch_index: int = Field(default=0, ge=0, alias="batchIndex")
    sessions: List[AiSession] = Field(min_length=1)

    @field_validator("sessions")
    @classmethod
    def _limit(cls, sessions: List[AiSession]) -> List[AiSession]:
        cap = int(os.environ.get("VW_AI_SESSIONS_BATCH_MAX", "1000"))
        if len(sessions) > cap:
            raise ValueError(f"batch exceeds max session count {cap}")
        return sessions


def _auth_enabled() -> bool:
    return os.environ.get("AUTH_ENABLED", "1") == "1"


def _require_key() -> bool:
    configured = os.environ.get("VW_TELEMETRY_REQUIRE_KEY")
    if configured is not None:
        return configured == "1"
    return _auth_enabled()


def _extract_token(request: Request) -> str:
    api_key = request.headers.get("x-api-key") or ""
    if api_key:
        return api_key.strip()
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return ""


def _check_ingest_auth(request: Request) -> None:
    if not _require_key():
        return
    expected = os.environ.get("VW_TELEMETRY_API_KEY") or ""
    if not expected:
        raise HTTPException(status_code=503, detail="Telemetry API key is not configured")
    if not secrets.compare_digest(_extract_token(request), expected):
        raise HTTPException(status_code=401, detail="Invalid telemetry credentials")


@router.post("/batches")
async def ingest_batch(batch: AiSessionBatch, request: Request) -> Dict[str, Any]:
    """Ingest one spool batch. Idempotent: re-POSTing a batch upserts."""
    _check_ingest_auth(request)
    payload = batch.model_dump(mode="python", by_alias=True)
    result = await store_session_batch(payload)
    return {"ok": True, **result}


@router.get("/summary")
async def ai_sessions_summary(
    days: Optional[int] = Query(None, ge=1, le=365 * 20,
                                description="Restrict to the last N days of activity"),
) -> Dict[str, Any]:
    """Totals plus per-tool, per-host and per-model rollups."""
    return await get_summary(days=days)


@router.get("/projects")
async def ai_sessions_projects(
    limit: int = Query(50, ge=1, le=500),
    days: Optional[int] = Query(None, ge=1, le=365 * 20),
) -> Dict[str, Any]:
    """Which projects consumed the most assistant time."""
    return await get_projects(limit=limit, days=days)


@router.get("/timeline")
async def ai_sessions_timeline(
    bucket: str = Query("day", pattern="^(day|week|month)$"),
    days: int = Query(90, ge=1, le=365 * 20),
) -> Dict[str, Any]:
    """Sessions / messages / tokens per bucket per tool, for charting."""
    return await get_timeline(bucket=bucket, days=days)


@router.get("/sessions/search")
async def ai_sessions_search(
    q: str = "",
    tool: Optional[str] = None,
    host: Optional[str] = None,
    project: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
) -> Dict[str, Any]:
    """Free-text search over titles and working directories."""
    return await search_sessions(q=q, tool=tool, host=host, project=project, limit=limit)

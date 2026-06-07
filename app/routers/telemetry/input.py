from __future__ import annotations

import os
import secrets
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator

from .db import get_input_summary, search_input_events, store_input_batch

router = APIRouter(prefix="/api/telemetry/input", tags=["telemetry-input"])


class InputEvent(BaseModel):
    event_id: str = Field(min_length=6, max_length=160)
    event_type: str = Field(min_length=1, max_length=64)
    timestamp: Optional[datetime] = None
    bucket_start: Optional[datetime] = None
    metrics: Dict[str, Any] = Field(default_factory=dict)
    dimensions: Dict[str, Any] = Field(default_factory=dict)
    checksum: Optional[str] = Field(default=None, max_length=128)

    @field_validator("metrics", "dimensions")
    @classmethod
    def _dict_only(cls, value: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(value, dict):
            raise ValueError("must be an object")
        return value


class InputBatch(BaseModel):
    schema_version: int = Field(ge=1, le=3)
    source: str = Field(min_length=1, max_length=80)
    host: Dict[str, Any] = Field(default_factory=dict)
    session_id: str = Field(min_length=6, max_length=160)
    batch_id: str = Field(min_length=6, max_length=160)
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    events: List[InputEvent] = Field(min_length=1)

    @field_validator("events")
    @classmethod
    def _limit_events(cls, events: List[InputEvent]) -> List[InputEvent]:
        max_events = int(os.environ.get("VW_TELEMETRY_BATCH_MAX_EVENTS", "500"))
        if len(events) > max_events:
            raise ValueError(f"batch exceeds max event count {max_events}")
        return events


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
async def ingest_batch(batch: InputBatch, request: Request) -> Dict[str, Any]:
    _check_ingest_auth(request)
    result = await store_input_batch(batch.model_dump(mode="python"))
    return {"ok": True, **result}


@router.get("/summary")
async def input_summary(hours: int = Query(24, ge=1, le=24 * 14)) -> Dict[str, Any]:
    return await get_input_summary(hours=hours)


@router.get("/events/search")
async def input_events_search(
    q: str = "",
    event_type: Optional[str] = None,
    session_id: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
) -> Dict[str, Any]:
    return await search_input_events(q=q, event_type=event_type, session_id=session_id, limit=limit)

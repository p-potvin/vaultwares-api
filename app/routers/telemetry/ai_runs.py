"""Model-run telemetry: ingest + the read endpoints vault-monitor uses.

Ingest mirrors the ai-sessions contract exactly (x-api-key, batch POST) so the
same drain script and the same key work for both spools. Read endpoints are
unauthenticated like the other telemetry summaries.
"""

from __future__ import annotations

import os
import secrets
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .ai_rollups_db import (
    get_rollup_timeline,
    provisional_runs,
    settle_costs,
    store_rollup_batch,
)
from .ai_runs_db import (
    get_errors,
    get_latency_histogram,
    get_summary,
    get_timeline,
    search_runs,
    store_run_batch,
)

router = APIRouter(prefix="/api/telemetry/ai-runs", tags=["telemetry-ai-runs"])

_STATUSES = {"ok", "error", "timeout", "cancelled", "rejected"}


class AiRun(BaseModel):
    # Recorders gain fields over time; unknown ones are folded into `extra` by
    # the persistence layer rather than rejected here.
    model_config = ConfigDict(extra="allow", protected_namespaces=())

    run_id: str = Field(min_length=1, max_length=64)
    parent_run_id: Optional[str] = Field(default=None, max_length=64)
    provider: str = Field(min_length=1, max_length=64)
    runtime: str = Field(min_length=1, max_length=64)
    model: str = Field(min_length=1, max_length=200)
    model_revision: Optional[str] = Field(default=None, max_length=120)
    quantization: Optional[str] = Field(default=None, max_length=40)
    task: Optional[str] = Field(default=None, max_length=40)

    host: Optional[str] = Field(default=None, max_length=120)
    project: Optional[str] = Field(default=None, max_length=200)
    service: Optional[str] = Field(default=None, max_length=120)
    session_id: Optional[str] = Field(default=None, max_length=200)
    caller: Optional[str] = Field(default=None, max_length=200)
    environment: Optional[str] = Field(default=None, max_length=40)

    queued_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    first_token_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    queue_ms: Optional[float] = Field(default=None, ge=0)
    ttft_ms: Optional[float] = Field(default=None, ge=0)
    duration_ms: Optional[float] = Field(default=None, ge=0)
    tokens_per_second: Optional[float] = Field(default=None, ge=0)

    input_tokens: Optional[int] = Field(default=None, ge=0)
    output_tokens: Optional[int] = Field(default=None, ge=0)
    cached_input_tokens: Optional[int] = Field(default=None, ge=0)
    reasoning_tokens: Optional[int] = Field(default=None, ge=0)
    total_tokens: Optional[int] = Field(default=None, ge=0)

    status: str = Field(default="ok", max_length=32)
    error_class: Optional[str] = Field(default=None, max_length=120)
    http_status: Optional[int] = Field(default=None, ge=0, le=999)
    retries: int = Field(default=0, ge=0)

    cost_usd: Optional[float] = Field(default=None, ge=0)
    credits_used: Optional[float] = Field(default=None, ge=0)

    @field_validator("status")
    @classmethod
    def _known_status(cls, value: str) -> str:
        # An unrecognised status would silently vanish from every status filter,
        # so it is normalised to 'error' at the edge instead.
        return value if value in _STATUSES else "error"


# Fields a PUBLIC surface (an HF Space serving strangers) may send. Mirrors
# vaultwares_adk.telemetry.record.PUBLIC_SURFACE_FIELDS and
# vault-inference/app/telemetry.py.
#
# This re-scrub is not redundant with the sender's. Filtering only at the sender
# trusts a client we do not control: a Space's posting key can leak, and
# whatever holds it can then POST arbitrary JSON at this endpoint. An allowlist
# (not a denylist) so that a new field never ships by default.
PUBLIC_SURFACE_FIELDS = frozenset({
    "run_id", "provider", "runtime", "model", "served_model", "task",
    "request_id", "queued_at", "started_at", "ended_at", "queue_ms", "ttft_ms",
    "duration_ms", "provider_ms", "tokens_per_second", "input_tokens",
    "output_tokens", "cached_input_tokens", "reasoning_tokens", "total_tokens",
    "status", "finish_reason", "error_class", "http_status", "retries",
    "cost_usd", "priced_exactly", "cost_state", "is_free", "role",
    "prompt_chars", "completion_chars", "image_count", "audio_seconds",
    "steps", "width", "height",
})


def scrub_public(run: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in run.items() if k in PUBLIC_SURFACE_FIELDS}


class AiRunBatch(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    schema_version: int = Field(default=1, ge=1, le=5, alias="schema")
    source: str = Field(default="vw-ai-runs", min_length=1, max_length=80)
    host: str = Field(min_length=1, max_length=120)
    collected_at: Optional[datetime] = Field(default=None, alias="collectedAt")
    batch_index: int = Field(default=0, ge=0, alias="batchIndex")
    public_surface: bool = Field(default=False, alias="publicSurface")
    runs: List[AiRun] = Field(min_length=1)

    @field_validator("runs")
    @classmethod
    def _limit(cls, runs: List[AiRun]) -> List[AiRun]:
        cap = int(os.environ.get("VW_AI_RUNS_BATCH_MAX", "1000"))
        if len(runs) > cap:
            raise ValueError(f"batch exceeds max run count {cap}")
        return runs


def _auth_enabled() -> bool:
    return os.environ.get("AUTH_ENABLED", "1") == "1"


def _require_key() -> bool:
    return bool(os.environ.get("VW_TELEMETRY_API_KEY"))


def _extract_token(request: Request) -> str:
    header = request.headers.get("x-api-key")
    if header:
        return header.strip()
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return ""


def _check_ingest_auth(request: Request) -> bool:
    """Authenticate the batch and return True if it came from a public surface.

    Public HF Spaces get their own write-only key. The *key* decides whether a
    batch is treated as public, not the client-supplied `publicSurface` flag —
    otherwise a leaked Space key could simply omit the flag and forge internal
    records carrying host and project names.
    """
    if not _auth_enabled() or not _require_key():
        return False

    supplied = _extract_token(request)
    internal = os.environ.get("VW_TELEMETRY_API_KEY", "")
    public = os.environ.get("VW_TELEMETRY_PUBLIC_API_KEY", "")

    # Constant-time so a wrong key cannot be recovered by timing the response.
    if supplied and internal and secrets.compare_digest(supplied, internal):
        return False
    if supplied and public and secrets.compare_digest(supplied, public):
        return True
    raise HTTPException(status_code=401, detail="invalid or missing telemetry api key")


def _filters(
    provider: Optional[str] = None,
    runtime: Optional[str] = None,
    model: Optional[str] = None,
    task: Optional[str] = None,
    project: Optional[str] = None,
    host: Optional[str] = None,
    status: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        k: v
        for k, v in {
            "provider": provider, "runtime": runtime, "model": model, "task": task,
            "project": project, "host": host, "status": status,
        }.items()
        if v
    }


@router.post("/batches")
async def ingest_batch(batch: AiRunBatch, request: Request) -> Dict[str, Any]:
    from_public_key = _check_ingest_auth(request)
    payload = batch.model_dump(by_alias=True, exclude_none=False)

    # Either signal marks the batch public; only the key can clear it.
    if from_public_key or batch.public_surface:
        payload["runs"] = [scrub_public(run) for run in payload.get("runs", [])]
        # A public surface must not name our machines either, so the envelope
        # host is replaced with the surface's own source name.
        payload["host"] = f"public:{batch.source}"[:120]
        payload["publicSurface"] = True

    return await store_run_batch(payload)


class AiRunRollup(BaseModel):
    # Recorders gain KPIs over time; unknown keys are ignored by the persistence
    # layer rather than rejected, same rule as the raw-run model.
    model_config = ConfigDict(extra="allow", protected_namespaces=())

    hour: datetime
    provider: str = Field(min_length=1, max_length=64)
    runtime: str = Field(min_length=1, max_length=64)
    model: str = Field(min_length=1, max_length=200)
    task: str = Field(default="unknown", max_length=40)
    project: str = Field(default="unknown", max_length=200)
    host: Optional[str] = Field(default=None, max_length=120)
    status: str = Field(default="ok", max_length=32)
    runs: int = Field(default=0, ge=0)
    failures: int = Field(default=0, ge=0)
    duration_hist: List[int] = Field(default_factory=list)

    @field_validator("duration_hist")
    @classmethod
    def _sane_hist(cls, hist: List[int]) -> List[int]:
        # Bounded and non-negative: the bins are summed straight into BIGINT[]
        # columns, so a hostile or buggy sender should not get to define length.
        if len(hist) > 32:
            raise ValueError("duration_hist too long")
        if any(x < 0 for x in hist):
            raise ValueError("duration_hist counts must be non-negative")
        return hist


class AiRunRollupBatch(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    schema_version: int = Field(default=1, ge=1, le=5, alias="schema")
    source: str = Field(default="vw-ai-runs", min_length=1, max_length=80)
    host: str = Field(min_length=1, max_length=120)
    collected_at: Optional[datetime] = Field(default=None, alias="collectedAt")
    batch_index: int = Field(default=0, ge=0, alias="batchIndex")
    grain: str = Field(default="hour", max_length=16)
    rollups: List[AiRunRollup] = Field(min_length=1)

    @field_validator("rollups")
    @classmethod
    def _limit(cls, rollups: List[AiRunRollup]) -> List[AiRunRollup]:
        cap = int(os.environ.get("VW_AI_ROLLUPS_BATCH_MAX", "5000"))
        if len(rollups) > cap:
            raise ValueError(f"batch exceeds max rollup count {cap}")
        return rollups


class SettleRequest(BaseModel):
    request_ids: List[str] = Field(min_length=1)
    cost_usd: float = Field(ge=0)
    billing_source: Optional[str] = Field(default=None, max_length=80)


@router.post("/rollups/batches")
async def ingest_rollup_batch(batch: AiRunRollupBatch, request: Request) -> Dict[str, Any]:
    from_public_key = _check_ingest_auth(request)
    if from_public_key:
        # A public Space reports its own usage as raw runs only. Letting it
        # write the durable hourly grain would let a leaked key rewrite our
        # aggregates wholesale, since rollup ingest is an overwrite.
        raise HTTPException(status_code=403, detail="public surfaces may not write rollups")
    return await store_rollup_batch(batch.model_dump(by_alias=True))


@router.post("/settle")
async def settle(body: SettleRequest, request: Request) -> Dict[str, Any]:
    """Replace provisional costs once the real figure is known.

    Write path, so it takes the internal key — and never the public one.
    """
    if _check_ingest_auth(request):
        raise HTTPException(status_code=403, detail="public surfaces may not settle costs")
    return await settle_costs(
        body.request_ids, body.cost_usd, billing_source=body.billing_source
    )


@router.get("/provisional")
async def provisional(
    limit: int = Query(default=500, ge=1, le=2000),
    days: int = Query(default=30, ge=1, le=3650),
) -> Dict[str, Any]:
    """Rows still awaiting a settled cost — the input to the hourly pass."""
    return await provisional_runs(limit, days)


@router.get("/rollups/timeline")
async def rollup_timeline(
    days: int = Query(default=90, ge=1, le=3650),
    bucket: str = Query(default="day"),
    provider: Optional[str] = None,
    runtime: Optional[str] = None,
    model: Optional[str] = None,
    project: Optional[str] = None,
) -> Dict[str, Any]:
    return await get_rollup_timeline(
        days, bucket, _filters(provider, runtime, model, project=project)
    )


@router.get("/summary")
async def ai_runs_summary(
    days: Optional[int] = Query(default=None, ge=1, le=3650),
    provider: Optional[str] = None,
    runtime: Optional[str] = None,
    model: Optional[str] = None,
    task: Optional[str] = None,
    project: Optional[str] = None,
    host: Optional[str] = None,
) -> Dict[str, Any]:
    return await get_summary(days, _filters(provider, runtime, model, task, project, host))


@router.get("/timeline")
async def ai_runs_timeline(
    bucket: str = Query(default="day"),
    days: int = Query(default=30, ge=1, le=3650),
    provider: Optional[str] = None,
    runtime: Optional[str] = None,
    model: Optional[str] = None,
    project: Optional[str] = None,
) -> Dict[str, Any]:
    return await get_timeline(bucket, days, _filters(provider, runtime, model, project=project))


@router.get("/latency")
async def ai_runs_latency(
    days: int = Query(default=30, ge=1, le=3650),
    provider: Optional[str] = None,
    model: Optional[str] = None,
    task: Optional[str] = None,
) -> Dict[str, Any]:
    return await get_latency_histogram(days, _filters(provider, model=model, task=task))


@router.get("/errors")
async def ai_runs_errors(
    days: int = Query(default=30, ge=1, le=3650),
    limit: int = Query(default=20, ge=1, le=200),
    provider: Optional[str] = None,
    model: Optional[str] = None,
    project: Optional[str] = None,
) -> Dict[str, Any]:
    return await get_errors(days, limit, _filters(provider, model=model, project=project))


@router.get("/runs")
async def ai_runs_list(
    days: Optional[int] = Query(default=None, ge=1, le=3650),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    provider: Optional[str] = None,
    runtime: Optional[str] = None,
    model: Optional[str] = None,
    task: Optional[str] = None,
    project: Optional[str] = None,
    host: Optional[str] = None,
    status: Optional[str] = None,
) -> Dict[str, Any]:
    return await search_runs(
        days, limit, offset,
        _filters(provider, runtime, model, task, project, host, status),
    )

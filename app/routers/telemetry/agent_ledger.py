from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field

from .agent_ledger_db import (
    get_agent_changes,
    get_agent_work_impact,
    search_agent_ledger_events,
    store_agent_ledger_events,
)
from .input import _check_ingest_auth

router = APIRouter(prefix="/api/ledger/agent", tags=["agent-ledger"])


class AgentLedgerEvent(BaseModel):
    id: str = Field(min_length=6, max_length=180)
    project: Optional[str] = Field(default=None, max_length=120)
    kind: Optional[str] = Field(default=None, max_length=120)
    summary: Optional[str] = Field(default=None, max_length=12000)

    class Config:
        extra = "allow"


class AgentLedgerBatch(BaseModel):
    events: List[AgentLedgerEvent] = Field(min_length=1, max_length=5000)


@router.post("/events")
async def ingest_event(event: AgentLedgerEvent, request: Request) -> Dict[str, Any]:
    _check_ingest_auth(request)
    return {"ok": True, **await store_agent_ledger_events([event.model_dump(mode="python")])}


@router.post("/events/batches")
async def ingest_events(batch: AgentLedgerBatch, request: Request) -> Dict[str, Any]:
    _check_ingest_auth(request)
    events = [event.model_dump(mode="python") for event in batch.events]
    return {"ok": True, **await store_agent_ledger_events(events)}


@router.get("/changes")
async def changes(limit: int = Query(500, ge=1, le=2000)) -> Dict[str, Any]:
    return await get_agent_changes(limit=limit)


@router.get("/work-impact")
async def work_impact() -> Dict[str, Any]:
    return await get_agent_work_impact()


@router.get("/events/search")
async def events_search(
    q: str = "",
    project: Optional[str] = None,
    kind: Optional[str] = None,
    model: Optional[str] = None,
    tool: Optional[str] = None,
    mcp_server: Optional[str] = None,
    date: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
) -> Dict[str, Any]:
    return await search_agent_ledger_events(
        q=q,
        project=project,
        kind=kind,
        model=model,
        tool=tool,
        mcp_server=mcp_server,
        date=date,
        limit=limit,
    )

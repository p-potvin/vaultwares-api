"""Telemetry and ledger routers owned by vaultwares-api."""

from fastapi import APIRouter

from .agent_ledger import router as agent_ledger_router
from .ai_runs import router as ai_runs_router
from .ai_sessions import router as ai_sessions_router
from .input import router as input_router

router = APIRouter()
router.include_router(input_router)
router.include_router(agent_ledger_router)
router.include_router(ai_sessions_router)
router.include_router(ai_runs_router)

__all__ = ["router"]

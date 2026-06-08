"""Telemetry and ledger routers owned by vaultwares-api."""

from fastapi import APIRouter

from .agent_ledger import router as agent_ledger_router
from .input import router as input_router

router = APIRouter()
router.include_router(input_router)
router.include_router(agent_ledger_router)

__all__ = ["router"]

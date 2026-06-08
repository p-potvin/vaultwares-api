"""Resolve canonical VaultWares ADK imports for pipelines modules."""

from __future__ import annotations

import sys
from pathlib import Path


def _ensure_adk_on_path() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    candidates = (
        repo_root / "vaultwares-adk",
        repo_root.parent / "vaultwares-adk",
    )
    for candidate in candidates:
        if (candidate / "vaultwares_adk" / "__init__.py").is_file():
            candidate_str = str(candidate)
            if candidate_str not in sys.path:
                sys.path.insert(0, candidate_str)
            return


_ensure_adk_on_path()

from vaultwares_adk import AgentStatus, ExtrovertAgent, RedisCoordinator  # noqa: E402
from agent_registry import AgentRegistry  # noqa: E402

__all__ = [
    "AgentRegistry",
    "AgentStatus",
    "ExtrovertAgent",
    "RedisCoordinator",
]

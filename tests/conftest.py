import pytest
import importlib
import sys
from pathlib import Path
from unittest.mock import MagicMock

REPO_ROOT = Path(__file__).resolve().parents[1]
for candidate in (REPO_ROOT / "vaultwares-adk", REPO_ROOT.parent / "vaultwares-adk"):
    if (candidate / "vaultwares_adk" / "__init__.py").is_file():
        sys.path.insert(0, str(candidate))
        break

agent_base = importlib.import_module("vaultwares_adk.agent_base")
redis_coordinator = importlib.import_module("vaultwares_adk.redis_coordinator")

@pytest.fixture(autouse=True)
def mock_redis_coordinator(monkeypatch):
    monkeypatch.setattr(redis_coordinator, "RedisCoordinator", MagicMock())
    monkeypatch.setattr(agent_base, "RedisCoordinator", MagicMock())

    # In case redis itself is accessed directly somewhere during instantiation
    import redis
    monkeypatch.setattr(redis, "Redis", MagicMock())

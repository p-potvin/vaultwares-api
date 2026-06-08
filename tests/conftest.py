import pytest
from unittest.mock import MagicMock
import vaultwares_agentciation.redis_coordinator
import vaultwares_agentciation.agent_base

@pytest.fixture(autouse=True)
def mock_redis_coordinator(monkeypatch):
    monkeypatch.setattr(vaultwares_agentciation.redis_coordinator, "RedisCoordinator", MagicMock())
    monkeypatch.setattr(vaultwares_agentciation.agent_base, "RedisCoordinator", MagicMock())

    # In case redis itself is accessed directly somewhere during instantiation
    import redis
    monkeypatch.setattr(redis, "Redis", MagicMock())

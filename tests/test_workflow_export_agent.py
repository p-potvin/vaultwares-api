"""Tests for WorkflowExportAgent logic."""
import pytest
from unittest.mock import MagicMock
from ai_model.workflow_export_agent import WorkflowExportAgent
from ai_model.shared_context import SharedContext

class DummyValidationUtils:
    @staticmethod
    def validate_context(schema, ctx):
        return []
    @staticmethod
    def report_error(ctx, agent, err):
        pass

class DummyEventBus:
    published = []
    @staticmethod
    def publish(event, payload):
        DummyEventBus.published.append((event, payload))

# Mock RedisCoordinator to prevent connection attempts during tests
@pytest.fixture(autouse=True)
def mock_redis(monkeypatch):
    monkeypatch.setattr("ai_model.workflow_export_agent.RedisCoordinator", MagicMock())

def test_export_to_comfyui_success(monkeypatch):
    monkeypatch.setattr("ai_model.validation_utils.ValidationUtils", DummyValidationUtils)
    monkeypatch.setattr("ai_model.event_bus.EventBus", DummyEventBus)
    agent = WorkflowExportAgent(SharedContext())
    result = agent.export_to_comfyui({"foo": "bar"})
    assert result["success"]
    assert "comfyui_workflow" in result
    assert DummyEventBus.published


def test_export_to_comfyui_validation_error(monkeypatch):
    class FailingValidation:
        @staticmethod
        def validate_context(schema, ctx):
            return ["bad input"]
        @staticmethod
        def report_error(ctx, agent, err):
            pass
    monkeypatch.setattr("ai_model.validation_utils.ValidationUtils", FailingValidation)
    monkeypatch.setattr("ai_model.event_bus.EventBus", DummyEventBus)
    agent = WorkflowExportAgent(SharedContext())
    result = agent.export_to_comfyui({"foo": "bar"})
    assert not result["success"]
    assert "errors" in result

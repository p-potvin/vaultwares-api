"""
AIModel Wrapper – multi-modal manipulation toolkit
====================================================

Top-level exports for the most commonly used classes and helpers so that
callers only need a single import::

    from ai_model import AIModel, ImageProcessor, VideoProcessor, TextProcessor

See README.md for full usage examples and workflow documentation.
"""

from ai_model.core.model import BaseModelWrapper
from ai_model.core.text_model import TextModelWrapper
from ai_model.image.processor import ImageProcessor
from ai_model.video.processor import VideoProcessor
from ai_model.text.processor import TextProcessor
from ai_model.workflows.base import Workflow
from ai_model.utils.device import DeviceManager
from ai_model.context_schema import ImageContext, VideoContext, TextContext, WorkflowContext
from vaultwares_agentciation import AgentRegistry
from ai_model.event_bus import EventBus

# Register core agents for discovery
AgentRegistry.register(
    'text', TextProcessor, 'Text generation, editing, VQA, prompt engineering', TextContext
)
AgentRegistry.register(
    'image', ImageProcessor, 'Image generation, editing, masking, inpainting', ImageContext
)
AgentRegistry.register(
    'video', VideoProcessor, 'Video generation, editing, analysis', VideoContext
)
AgentRegistry.register(
    'workflow', Workflow, 'Workflow parsing, export, validation', WorkflowContext
)


__version__ = "0.1.0"

__all__ = [
    "BaseModelWrapper",
    "TextModelWrapper",
    "ImageProcessor",
    "VideoProcessor",
    "TextProcessor",
    "Workflow",
    "DeviceManager",
]

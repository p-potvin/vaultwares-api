"""
High-level :class:`TextProcessor` for text and prompt operations.

Usage::

    from ai_model import SmolVLM2Wrapper
    from ai_model import TextModelWrapper
    from ai_model.text.processor import TextProcessor
    from PIL import Image

    model = TextModelWrapper()
    tp = TextProcessor(model=model)

    caption = tp.caption(Image.open("photo.jpg"), style="detailed")
    enhanced = tp.enhance_prompt("a beach sunset")
    answer  = tp.vqa("How many people?", images=[Image.open("crowd.jpg")])
"""

from __future__ import annotations

import logging
import random
import string
from typing import Any, List, Optional

from PIL import Image

from ai_model.text.prompts import (
    build_caption_prompt,
    build_vqa_prompt,
    build_enhancement_prompt,
    build_video_description_prompt,
    STYLE_PROMPTS,
)

from ai_model.adk_imports import AgentStatus, ExtrovertAgent

logger = logging.getLogger(__name__)


class TextProcessor(ExtrovertAgent):
    """Fluent text-generation interface backed by any model wrapper.

    Parameters
    ----------
    model:
        Any object with a compatible ``generate(prompt, images, videos)``
        method (e.g. :class:`~ai_model.core.text.TextModelWrapper`).
    """

    def __init__(self, model=None) -> None:
        # Generate unique agent ID: text-XXXX
        agent_id = 'text-' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
        super().__init__(agent_id=agent_id)
        
        self._model = model
        self.start()

    def _require_model(self) -> None:
        if self._model is None:
            raise RuntimeError(
                "No model attached.  Pass model=GenericTextModelWrapper() to TextProcessor."
            )

    # ------------------------------------------------------------------ #
    # captioning                                                           #
    # ------------------------------------------------------------------ #

    def caption(
        self,
        image: Image.Image,
        style: str = "detailed",
        **kwargs: Any,
    ) -> str:
        """Generate a caption for *image*."""
        self.update_status(AgentStatus.WORKING)
        self._require_model()
        prompt = build_caption_prompt(style)
        res = self._model.generate(prompt, images=[image], **kwargs)
        self.update_status(AgentStatus.WAITING_FOR_INPUT)
        return res

    # ------------------------------------------------------------------ #
    # VQA                                                                  #
    # ------------------------------------------------------------------ #

    def vqa(
        self,
        question: str,
        images: Optional[List[Image.Image]] = None,
        **kwargs: Any,
    ) -> str:
        """Visual question answering."""
        self.update_status(AgentStatus.WORKING)
        self._require_model()
        prompt = build_vqa_prompt(question)
        res = self._model.generate(prompt, images=images, **kwargs)
        self.update_status(AgentStatus.WAITING_FOR_INPUT)
        return res

    # ------------------------------------------------------------------ #
    # prompt enhancement                                                   #
    # ------------------------------------------------------------------ #

    def enhance_prompt(
        self,
        prompt: str,
        image: Optional[Image.Image] = None,
        **kwargs: Any,
    ) -> str:
        """Rewrite and enrich *prompt* to be more descriptive."""
        self.update_status(AgentStatus.WORKING)
        self._require_model()
        full_prompt = build_enhancement_prompt(prompt)
        res = self._model.generate(full_prompt, images=[image] if image else None, **kwargs)
        self.update_status(AgentStatus.WAITING_FOR_INPUT)
        return res
    def describe_video(
        self,
        frames: List[Image.Image],
        focus: str = "action",
        **kwargs: Any,
    ) -> str:
        """Describe a video clip given a list of frames."""
        self.update_status(AgentStatus.WORKING)
        self._require_model()
        full_prompt = build_video_description_prompt(focus)
        res = self._model.generate(full_prompt, videos=[frames], **kwargs)
        self.update_status(AgentStatus.WAITING_FOR_INPUT)
        return res
    def batch_caption(
        self,
        images: List[Image.Image],
        style: str = "brief",
    ) -> List[str]:
        """Caption multiple images in sequence."""
        return [self.caption(img, style=style) for img in images]

    def batch_vqa(
        self,
        question: str,
        images: List[Image.Image],
    ) -> List[str]:
        """Ask the same *question* about each image.
        return [self.vqa(question, images=[img]) for img in images]
            Question to ask.
        images:
            List of images.

        Returns
        -------
        List[str]
            Answers in the same order as *images*.

        Example::

            answers = tp.batch_vqa("Is there a person?", [img1, img2])
        """
        return [self.vqa(question, images=[img]) for img in images]

    # ------------------------------------------------------------------ #
    # list available styles                                                #
    # ------------------------------------------------------------------ #

    @staticmethod
    def available_styles() -> List[str]:
        """Return the list of available caption styles.

        Returns
        -------
        List[str]
            Style names.

        Example::

            print(TextProcessor.available_styles())
        """
        return list(STYLE_PROMPTS.keys())

"""
High-level :class:`VideoProcessor` that chains video operations and
optional SmolVLM2 analysis into a single fluent interface.

Usage (standalone)::

    from ai_model.video.processor import VideoProcessor

    proc = VideoProcessor()
    proc.load("clip.mp4") \
        .trim(start=0, end=60) \
        .resize(640, 360) \
        .apply_effect(lambda f: sharpen(f, percent=130)) \
        .save("output.mp4", fps=30)

Usage (with model)::

    from ai_model import SmolVLM2Wrapper, VideoProcessor

    model = SmolVLM2Wrapper()
    proc  = VideoProcessor(model=model)
    description = proc.load("clip.mp4").sample(8).describe()
"""

from __future__ import annotations

import logging
import random
import string
from pathlib import Path
from typing import Any, Callable, List, Optional, Tuple, Union

from PIL import Image

from ai_model.video import manipulation, utils as vid_utils
from ai_model.adk_imports import AgentStatus, ExtrovertAgent

logger = logging.getLogger(__name__)


class VideoProcessor(ExtrovertAgent):
    """Chainable video processing pipeline with optional model integration.

    Parameters
    ----------
    model:
        Optional :class:`~ai_model.core.model.BaseModelWrapper`.
        Enables :meth:`describe` and :meth:`caption_frames`.
    """

    def __init__(self, model=None) -> None:
        # Generate unique agent ID: video-XXXX
        agent_id = 'video-' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
        super().__init__(agent_id=agent_id)
        
        self._model = model
        self._frames: List[Image.Image] = []
        self._fps: float = 24.0
        self.start()

    # ------------------------------------------------------------------ #
    # I/O                                                                  #
    # ------------------------------------------------------------------ #

    def load(self, source: Union[str, Path], max_frames: int = 0) -> "VideoProcessor":
        """Load a video file into memory as PIL frames.

        Parameters
        ----------
        source:
            Path to a video file.
        max_frames:
            Maximum frames to load (0 = all frames).

        Returns
        -------
        VideoProcessor
            Self (for chaining).

        Example::

            proc.load("clip.mp4")
        """
        from ai_model.utils.io import load_video
        try:
            import cv2
            cap = cv2.VideoCapture(str(source))
            self._fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
            cap.release()
        except Exception:
            self._fps = 24.0
        self._frames = load_video(source, max_frames=max_frames)
        logger.debug("Loaded %d frames at %.1f fps", len(self._frames), self._fps)
        return self

    def sample(self, n: int = 8) -> "VideoProcessor":
        """Evenly sample *n* frames from the currently loaded video.

        Parameters
        ----------
        n:
            Number of frames to keep.

        Returns
        -------
        VideoProcessor
            Self (for chaining).

        Example::

            proc.load("clip.mp4").sample(8).describe()
        """
        if not self._frames:
            return self
        total = len(self._frames)
        indices = [int(i * (total - 1) / max(n - 1, 1)) for i in range(n)]
        self._frames = [self._frames[i] for i in indices]
        return self

    def set_frames(self, frames: List[Image.Image], fps: float = 24.0) -> "VideoProcessor":
        """Set frames directly (e.g. from another processor).

        Parameters
        ----------
        frames:
            List of PIL frames.
        fps:
            Playback frame-rate for saving.

        Returns
        -------
        VideoProcessor
            Self.
        """
        self._frames = frames
        self._fps = fps
        return self

    def get_frames(self) -> List[Image.Image]:
        """Return the current frame list."""
        return self._frames

    def save(self, dest: Union[str, Path], fps: Optional[float] = None) -> Path:
        """Encode frames to a video file.

        Parameters
        ----------
        dest:
            Output file path (extension determines container, e.g. ``.mp4``).
        fps:
            Override frame rate (default: the rate detected on load, or 24).

        Returns
        -------
        pathlib.Path
            Path to the saved video.

        Example::

            proc.load("clip.mp4").resize(640, 360).save("small.mp4")
        """
        from ai_model.utils.io import save_video
        return save_video(self._frames, dest, fps=fps or self._fps)

    def save_gif(self, dest: Union[str, Path], fps: float = 10.0) -> Path:
        """Export frames as an animated GIF.

        Parameters
        ----------
        dest:
            Output ``.gif`` path.
        fps:
            GIF frame rate.

        Returns
        -------
        pathlib.Path
            Path to the GIF.

        Example::

            proc.load("clip.mp4").sample(20).save_gif("preview.gif")
        """
        return vid_utils.frames_to_gif(self._frames, dest, fps=fps)

    # ------------------------------------------------------------------ #
    # manipulation                                                         #
    # ------------------------------------------------------------------ #

    def trim(self, start: int = 0, end: Optional[int] = None) -> "VideoProcessor":
        """Trim to frame range [*start*, *end*).

        Example::

            proc.load("clip.mp4").trim(0, 60).save("first_60.mp4")
        """
        self._frames = manipulation.trim_frames(self._frames, start=start, end=end)
        return self

    def resize(self, width: int, height: int) -> "VideoProcessor":
        """Resize every frame.

        Example::

            proc.load("clip.mp4").resize(320, 180).save("small.mp4")
        """
        self._frames = manipulation.resize_frames(self._frames, width, height)
        return self

    def reverse(self) -> "VideoProcessor":
        """Reverse the frame order.

        Example::

            proc.load("clip.mp4").reverse().save("reversed.mp4")
        """
        self._frames = manipulation.reverse_frames(self._frames)
        return self

    def apply_effect(self, effect: Callable[[Image.Image], Image.Image]) -> "VideoProcessor":
        """Apply an image effect to every frame.

        Parameters
        ----------
        effect:
            Callable ``Image → Image``.  Any function from
            :mod:`ai_model.image.manipulation` works here.

        Example::

            from ai_model.image.manipulation import sharpen
            proc.load("clip.mp4").apply_effect(lambda f: sharpen(f, percent=150)).save("sharp.mp4")
        """
        self._frames = manipulation.apply_frame_effect(self._frames, effect)
        return self

    def add_overlay(
        self,
        overlay: Image.Image,
        alpha: float = 0.3,
        position: Tuple[int, int] = (0, 0),
    ) -> "VideoProcessor":
        """Overlay an image on every frame.

        Parameters
        ----------
        overlay:
            Image to composite.
        alpha:
            Opacity 0–1.
        position:
            ``(x, y)`` top-left anchor.

        Example::

            logo = Image.open("logo.png")
            proc.load("clip.mp4").add_overlay(logo, alpha=0.2).save("branded.mp4")
        """
        self._frames = manipulation.add_frame_overlay(
            self._frames, overlay, alpha=alpha, position=position
        )
        return self

    def stabilize(self) -> "VideoProcessor":
        """Reduce camera shake using feature-based stabilisation.

        Requires ``opencv-python``.  Degrades gracefully to a no-op if OpenCV
        is not installed.

        Example::

            proc.load("shaky.mp4").stabilize().save("stable.mp4")
        """
        self._frames = manipulation.stabilize_frames(self._frames)
        return self

    # ------------------------------------------------------------------ #
    # model-powered operations                                             #
    # ------------------------------------------------------------------ #

    def describe(
        self,
        prompt: str = "Describe what is happening in this video.",
    ) -> str:
        """Generate a natural-language description using the attached model."""
        self.update_status(AgentStatus.WORKING)
        if self._model is None:
            self.update_status(AgentStatus.WAITING_FOR_INPUT)
            raise RuntimeError("No model attached.  Pass model=SmolVLM2Wrapper() to VideoProcessor.")
        
        try:
            if hasattr(self._model, 'describe_video'):
                res = self._model.describe_video(self._frames, prompt=prompt)
            else:
                res = self._model.generate(prompt, images=self._frames)
        finally:
            self.update_status(AgentStatus.WAITING_FOR_INPUT)
        return res

    def caption_frames(
        self,
        style: str = "brief",
        every_n: int = 1,
    ) -> List[str]:
        """Generate a caption for every N-th frame.

        Parameters
        ----------
        style:
            Caption style (``"brief"``, ``"detailed"``, ``"tags"``).
        every_n:
            Caption every *every_n* frames.

        Returns
        -------
        List[str]
            One caption per sampled frame.

        Example::

            captions = VideoProcessor(model=SmolVLM2Wrapper()) \
                .load("clip.mp4").sample(16).caption_frames(every_n=4)
        """
        if self._model is None:
            raise RuntimeError("No model attached.")
        return [
            self._model.caption(frame, style=style)
            for frame in self._frames[::every_n]
        ]

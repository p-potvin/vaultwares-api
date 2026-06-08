"""
Video utility functions.

* :func:`sample_frames`  – evenly sample N frames from a video file
* :func:`frames_to_gif`  – convert frames to an animated GIF
* :func:`add_audio`      – mux audio track into a video file
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional, Union

from PIL import Image


def sample_frames(
    source: Union[str, Path],
    n: int = 8,
) -> List[Image.Image]:
    """Evenly sample *n* frames from a video file.

    Parameters
    ----------
    source:
        Path to a video file.
    n:
        Number of frames to sample.

    Returns
    -------
    List[PIL.Image.Image]
        Sampled frames in chronological order.

    Raises
    ------
    ImportError
        If ``opencv-python`` is not installed.

    Example::

        from ai_model.video.utils import sample_frames
        frames = sample_frames("clip.mp4", n=8)
    """
    try:
        import cv2
    except ImportError as exc:
        raise ImportError(
            "opencv-python is required.  Install with: pip install opencv-python"
        ) from exc

    path = Path(source)
    if not path.exists():
        raise FileNotFoundError(f"Video not found: {path}")

    cap = cv2.VideoCapture(str(path))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total <= 0:
        total = 1

    indices = [int(i * (total - 1) / max(n - 1, 1)) for i in range(n)]
    frames: List[Image.Image] = []
    for idx in indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = cap.read()
        if ret:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frames.append(Image.fromarray(rgb))
    cap.release()
    return frames


def frames_to_gif(
    frames: List[Image.Image],
    dest: Union[str, Path],
    fps: float = 10.0,
    loop: int = 0,
) -> Path:
    """Save a list of frames as an animated GIF.

    Parameters
    ----------
    frames:
        Ordered frame list.
    dest:
        Output ``.gif`` file path.
    fps:
        Frames per second (determines frame duration).
    loop:
        Number of loop repetitions (0 = infinite).

    Returns
    -------
    pathlib.Path
        Path to the saved GIF.

    Example::

        frames_to_gif(highlight_frames, "highlight.gif", fps=5)
    """
    if not frames:
        raise ValueError("frames must not be empty.")

    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    duration = int(1000 / fps)
    frames[0].save(
        dest,
        save_all=True,
        append_images=frames[1:],
        duration=duration,
        loop=loop,
        optimize=False,
    )
    return dest.resolve()


def add_audio(
    video_path: Union[str, Path],
    audio_path: Union[str, Path],
    output_path: Union[str, Path],
) -> Path:
    """Mux *audio_path* into *video_path* and write the result to *output_path*.

    Requires ``ffmpeg`` to be available on the ``PATH``.

    Parameters
    ----------
    video_path:
        Input video file (any format supported by ffmpeg).
    audio_path:
        Input audio file.
    output_path:
        Output file path.

    Returns
    -------
    pathlib.Path
        Path to the output file.

    Raises
    ------
    RuntimeError
        If ffmpeg is not found or the muxing command fails.

    Example::

        add_audio("silent.mp4", "music.mp3", "with_audio.mp4")
    """
    import subprocess

    video_path = Path(video_path)
    audio_path = Path(audio_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-c:v", "copy",
        "-c:a", "aac",
        "-shortest",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        # Prevent information leakage by not including the full stderr in the exception
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"ffmpeg failed with return code {result.returncode}: {result.stderr}")
        raise RuntimeError("An error occurred during video processing. Please check the logs.")
    return output_path.resolve()

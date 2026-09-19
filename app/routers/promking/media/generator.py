"""
Prom-King OnlyFans Media Generator.
Invokes ffmpeg and ffprobe via asyncio subprocess to generate animated previews,
tiled sprite sheets, and WebVTT scrubbing tracks from source MP4 streams.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import shutil
from pathlib import Path

from .storage import get_video_media_dir, get_media_url

logger = logging.getLogger("promking.media.generator")

FFMPEG_HEADERS = "Referer: https://notfans.com/\r\nUser-Agent: Mozilla/5.0\r\n"


def _format_vtt_time(seconds: float) -> str:
    """Formats seconds into WebVTT timestamp format: HH:MM:SS.mmm."""
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    return f"{hrs:02d}:{mins:02d}:{secs:02d}.{millis:03d}"


async def probe_video_duration(video_url: str) -> float | None:
    """Probes the remote video using ffprobe to obtain duration in seconds."""
    ffprobe_bin = shutil.which("ffprobe") or "ffprobe"
    cmd = [
        ffprobe_bin,
        "-v", "error",
        "-headers", FFMPEG_HEADERS,
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        video_url,
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30.0)
        if proc.returncode == 0:
            text = stdout.decode().strip()
            val = float(text)
            if val > 0:
                return val
    except Exception as exc:
        logger.warning("ffprobe failed for %s: %s", video_url, exc)
    return None


async def generate_animated_preview(
    video_id: int,
    video_url: str,
    duration: float,
    clip_seconds: float = 4.0,
) -> str | None:
    """
    Generates a lightweight looping animated preview MP4 clip (no audio, scaled).
    Returns the public API URL (/api/promking/media/onlyfans/{video_id}/preview.mp4).
    """
    v_dir = get_video_media_dir(video_id)
    preview_file = v_dir / "preview.mp4"

    if preview_file.exists() and preview_file.stat().st_size > 1000:
        return get_media_url(video_id, "preview.mp4")

    ffmpeg_bin = shutil.which("ffmpeg") or "ffmpeg"
    # Choose start point: ~10% into the video or 5 seconds in, but ensuring at least clip_seconds remain
    start_time = 5.0
    if duration > (clip_seconds + 10):
        start_time = max(5.0, duration * 0.1)

    cmd = [
        ffmpeg_bin,
        "-y",
        "-ss", f"{start_time:.2f}",
        "-t", f"{clip_seconds:.2f}",
        "-headers", FFMPEG_HEADERS,
        "-i", video_url,
        "-an",
        "-vf", "scale=320:-2",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "28",
        "-movflags", "+faststart",
        str(preview_file),
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=60.0)
        if proc.returncode == 0 and preview_file.exists() and preview_file.stat().st_size > 1000:
            logger.info("Generated preview.mp4 for video %s (%s bytes)", video_id, preview_file.stat().st_size)
            return get_media_url(video_id, "preview.mp4")
        else:
            logger.warning(
                "ffmpeg preview generation failed for video %s (code %s): %s",
                video_id,
                proc.returncode,
                stderr.decode(errors="replace")[-300:],
            )
    except Exception as exc:
        logger.error("Exception generating preview for video %s: %s", video_id, exc)

    return None


async def generate_sprite_sheet(
    video_id: int,
    video_url: str,
    duration: float,
    tile_count: int = 30,
    tiles_per_row: int = 6,
    tile_width: int = 160,
    tile_height: int = 90,
) -> tuple[str | None, str | None, dict]:
    """
    Extracts equidistant frames across the video and tiles them into a single sprite sheet image.
    Also produces a WebVTT file with frame time cues for timeline scrubbing.
    Returns: (sprite_url, sprite_vtt_url, metadata_dict).
    """
    v_dir = get_video_media_dir(video_id)
    sprite_file = v_dir / "sprite.jpg"
    vtt_file = v_dir / "sprite.vtt"

    meta = {
        "tile_width": tile_width,
        "tile_height": tile_height,
        "tile_count": tile_count,
        "tiles_per_row": tiles_per_row,
        "interval_seconds": 0.0,
    }

    if duration <= 0:
        duration = 180.0

    interval = max(1.0, duration / float(tile_count))
    meta["interval_seconds"] = round(interval, 2)
    rows = math.ceil(tile_count / tiles_per_row)

    ffmpeg_bin = shutil.which("ffmpeg") or "ffmpeg"
    vf_filter = (
        f"fps=1/{interval:.4f},"
        f"scale={tile_width}:{tile_height}:force_original_aspect_ratio=decrease,"
        f"pad={tile_width}:{tile_height}:(ow-iw)/2:(oh-ih)/2:black,"
        f"tile={tiles_per_row}x{rows}"
    )

    sprite_created = False
    if sprite_file.exists() and sprite_file.stat().st_size > 1000:
        sprite_created = True
    else:
        cmd = [
            ffmpeg_bin,
            "-y",
            "-threads", "2",
            "-headers", FFMPEG_HEADERS,
            "-ss", "00:00:00",
            "-skip_frame", "nokey",
            "-i", video_url,
            "-vf", vf_filter,
            "-frames:v", "1",
            "-update", "1",
            "-q:v", "3",
            str(sprite_file),
        ]
        proc = None
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=max(120.0, duration * 0.15))
            if proc.returncode == 0 and sprite_file.exists() and sprite_file.stat().st_size > 1000:
                sprite_created = True
                logger.info("Generated sprite.jpg for video %s (%s bytes)", video_id, sprite_file.stat().st_size)
            else:
                logger.warning(
                    "ffmpeg sprite generation failed for video %s (code %s): %s",
                    video_id,
                    proc.returncode,
                    stderr.decode(errors="replace")[-300:],
                )
        except asyncio.TimeoutError:
            if proc:
                try:
                    proc.kill()
                    await proc.wait()
                except Exception:
                    pass
            logger.warning("ffmpeg sprite generation timed out for video %s", video_id)
        except Exception as exc:
            if proc:
                try:
                    proc.kill()
                    await proc.wait()
                except Exception:
                    pass
            logger.error("Exception generating sprite for video %s: %s", video_id, exc)

    sprite_url = get_media_url(video_id, "sprite.jpg") if sprite_created else None

    # Generate WebVTT
    vtt_url = None
    if sprite_created:
        vtt_lines = ["WEBVTT\n"]
        for i in range(tile_count):
            start = i * interval
            end = min(duration, (i + 1) * interval)
            col = i % tiles_per_row
            row = i // tiles_per_row
            x = col * tile_width
            y = row * tile_height

            start_str = _format_vtt_time(start)
            end_str = _format_vtt_time(end)
            cue = f"{start_str} --> {end_str}\nsprite.jpg#xywh={x},{y},{tile_width},{tile_height}\n"
            vtt_lines.append(cue)

        vtt_file.write_text("\n".join(vtt_lines), encoding="utf-8")
        vtt_url = get_media_url(video_id, "sprite.vtt")

    return sprite_url, vtt_url, meta

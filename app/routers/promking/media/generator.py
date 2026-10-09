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


async def has_audio_stream(video_url: str) -> bool:
    """Probes whether the video contains an audio stream."""
    ffprobe_bin = shutil.which("ffprobe") or "ffprobe"
    cmd = [
        ffprobe_bin,
        "-v", "error",
        "-headers", FFMPEG_HEADERS,
        "-select_streams", "a:0",
        "-show_entries", "stream=codec_type",
        "-of", "default=noprint_wrappers=1:nokey=1",
        video_url,
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15.0)
        return proc.returncode == 0 and "audio" in stdout.decode().lower()
    except Exception:
        return False


def compute_staggered_capture_offsets(
    duration: float | None,
    captures_count: int = 7,
    capture_duration: float = 1.5,
    default_start_offset: float = 15.0,
) -> list[float]:
    """Calculates staggered start offsets evenly distributed throughout a video."""
    total_time = captures_count * capture_duration
    if not duration or duration <= (total_time + 2):
        base = max(0.0, default_start_offset)
        return [round(base + i * capture_duration, 2) for i in range(captures_count)]

    start_margin = max(3.0, min(20.0, duration * 0.05))
    end_margin = max(3.0, min(20.0, duration * 0.05))
    usable = duration - start_margin - end_margin - capture_duration

    if usable > 0:
        step = usable / (captures_count - 1)
        return [round(start_margin + i * step, 2) for i in range(captures_count)]

    step = max(0.0, (duration - capture_duration) / (captures_count - 1))
    return [round(i * step, 2) for i in range(captures_count)]


async def generate_animated_preview(
    video_id: int,
    video_url: str,
    duration: float,
    captures_count: int = 7,
    capture_duration: float = 1.5,
    volume: float = 0.5,
    clip_seconds: float | None = None,
) -> str | None:
    """
    Generates a 7-capture staggered highlight preview MP4 clip (1.5s each, 10.5s total)
    spliced together with audio volume reduced to ~0.5.
    Returns the public API URL (/api/promking/media/onlyfans/{video_id}/preview.mp4).
    """
    v_dir = get_video_media_dir(video_id)
    preview_file = v_dir / "preview.mp4"

    if preview_file.exists() and preview_file.stat().st_size > 1000:
        return get_media_url(video_id, "preview.mp4")

    ffmpeg_bin = shutil.which("ffmpeg") or "ffmpeg"
    audio_available = await has_audio_stream(video_url)
    offsets = compute_staggered_capture_offsets(duration, captures_count, capture_duration)

    # Multi-input spliced command
    cmd = [ffmpeg_bin, "-y"]
    filter_parts: list[str] = []
    concat_str = ""

    for i, off in enumerate(offsets):
        cmd.extend([
            "-headers", FFMPEG_HEADERS,
            "-reconnect", "1",
            "-reconnect_streamed", "1",
            "-reconnect_delay_max", "5",
            "-ss", f"{off:.2f}",
            "-t", f"{capture_duration:.2f}",
            "-i", video_url,
        ])
        filter_parts.append(f"[{i}:v]scale=320:-2,setsar=1,fps=30[v{i}]")
        if audio_available:
            filter_parts.append(f"[{i}:a]volume={volume},aformat=sample_rates=44100:channel_layouts=stereo[a{i}]")
            concat_str += f"[v{i}][a{i}]"
        else:
            concat_str += f"[v{i}]"

    a_count = 1 if audio_available else 0
    filter_parts.append(f"{concat_str}concat=n={captures_count}:v=1:a={a_count}[outv]{'[outa]' if audio_available else ''}")

    cmd.extend(["-filter_complex", "; ".join(filter_parts), "-map", "[outv]"])
    if audio_available:
        cmd.extend(["-map", "[outa]", "-c:a", "aac", "-b:a", "64k"])

    cmd.extend([
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "28",
        "-movflags", "+faststart",
        str(preview_file),
    ])

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=90.0)
        if proc.returncode == 0 and preview_file.exists() and preview_file.stat().st_size > 1000:
            logger.info("Generated spliced preview.mp4 for video %s (%s bytes)", video_id, preview_file.stat().st_size)
            return get_media_url(video_id, "preview.mp4")
        else:
            logger.warning(
                "ffmpeg multi-clip preview generation failed for video %s (code %s): %s, attempting single-clip fallback",
                video_id,
                proc.returncode,
                stderr.decode(errors="replace")[-300:],
            )
    except Exception as exc:
        logger.warning("Exception during multi-clip preview for video %s: %s, attempting fallback", video_id, exc)

    # Fallback to single continuous clip with volume reduction
    try:
        total_len = clip_seconds if clip_seconds is not None else (captures_count * capture_duration)
        start_time = max(5.0, duration * 0.1) if duration > 20 else 5.0
        fallback_cmd = [
            ffmpeg_bin,
            "-y",
            "-headers", FFMPEG_HEADERS,
            "-reconnect", "1",
            "-reconnect_streamed", "1",
            "-reconnect_delay_max", "5",
            "-ss", f"{start_time:.2f}",
            "-t", f"{total_len:.2f}",
            "-i", video_url,
            "-vf", "scale=320:-2",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "28",
        ]
        if audio_available:
            fallback_cmd.extend(["-af", f"volume={volume}", "-c:a", "aac", "-b:a", "64k"])
        else:
            fallback_cmd.append("-an")
        fallback_cmd.extend(["-movflags", "+faststart", str(preview_file)])

        proc = await asyncio.create_subprocess_exec(
            *fallback_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=60.0)
        if proc.returncode == 0 and preview_file.exists() and preview_file.stat().st_size > 1000:
            logger.info("Generated fallback preview.mp4 for video %s (%s bytes)", video_id, preview_file.stat().st_size)
            return get_media_url(video_id, "preview.mp4")
    except Exception as exc:
        logger.error("Exception generating fallback preview for video %s: %s", video_id, exc)

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

import asyncio
from pathlib import Path

from app.routers.promking.media import generator


class _FakeProc:
    def __init__(self, returncode: int = 0) -> None:
        self.returncode = returncode

    async def communicate(self):
        return b"", b""

    def kill(self) -> None:
        pass

    async def wait(self) -> None:
        pass


def test_generate_sprite_sheet_uses_pooled_seeks_on_long_remote_stream(tmp_path, monkeypatch):
    monkeypatch.setenv("PROMKING_MEDIA_DIR", str(tmp_path))
    commands: list[tuple[str, ...]] = []

    async def fake_exec(*cmd, **_kwargs):
        commands.append(cmd)
        out = Path(cmd[-1])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"x" * 2048)
        return _FakeProc(0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    sprite_url, vtt_url, meta = asyncio.run(
        generator.generate_sprite_sheet(
            video_id=12345,
            video_url="https://notfans.com/get_file/1/video.mp4",
            duration=300.0,
            tile_count=6,
            tiles_per_row=3,
            tile_width=160,
            tile_height=90,
        )
    )

    assert sprite_url == "/api/promking/media/onlyfans/12345/sprite.jpg"
    assert vtt_url == "/api/promking/media/onlyfans/12345/sprite.vtt"
    assert meta["interval_seconds"] == 50.0
    # 6 tile extractions + 1 stitch call
    assert len(commands) == 7
    tile_cmds = commands[:6]
    assert all("-noaccurate_seek" in c and "-ss" in c for c in tile_cmds)
    assert all("-skip_frame" not in c for c in tile_cmds)
    seeks = [c[c.index("-ss") + 1] for c in tile_cmds]
    assert seeks == ["0.00", "50.00", "100.00", "150.00", "200.00", "250.00"]
    assert "tile=3x2" in commands[-1][commands[-1].index("-filter_complex") + 1]
    assert (tmp_path / "12345" / "sprite.jpg").exists()
    vtt_text = (tmp_path / "12345" / "sprite.vtt").read_text(encoding="utf-8")
    assert "sprite.jpg#xywh=320,90,160,90" in vtt_text


def test_generate_sprite_sheet_falls_back_to_single_pass_when_seek_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("PROMKING_MEDIA_DIR", str(tmp_path))
    commands: list[tuple[str, ...]] = []

    async def fake_exec(*cmd, **_kwargs):
        commands.append(cmd)
        # Fail tile index 2 on both attempts, succeed for single-pass fallback
        if "-noaccurate_seek" in cmd:
            if "tile_002" in cmd[-1]:
                return _FakeProc(1)
            Path(cmd[-1]).write_bytes(b"x" * 512)
            return _FakeProc(0)
        Path(cmd[-1]).write_bytes(b"y" * 2048)
        return _FakeProc(0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    sprite_url, vtt_url, _ = asyncio.run(
        generator.generate_sprite_sheet(
            video_id=12346,
            video_url="https://notfans.com/get_file/1/video.mp4",
            duration=120.0,
            tile_count=4,
            tiles_per_row=2,
        )
    )

    assert sprite_url == "/api/promking/media/onlyfans/12346/sprite.jpg"
    assert vtt_url == "/api/promking/media/onlyfans/12346/sprite.vtt"
    assert any("-skip_frame" in c and "nokey" in c for c in commands)


def test_generate_sprite_sheet_uses_single_pass_for_short_or_local_video(tmp_path, monkeypatch):
    monkeypatch.setenv("PROMKING_MEDIA_DIR", str(tmp_path))
    commands: list[tuple[str, ...]] = []

    async def fake_exec(*cmd, **_kwargs):
        commands.append(cmd)
        Path(cmd[-1]).write_bytes(b"z" * 2048)
        return _FakeProc(0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    sprite_url, vtt_url, _ = asyncio.run(
        generator.generate_sprite_sheet(
            video_id=12347,
            video_url="https://notfans.com/get_file/1/short.mp4",
            duration=12.0,
            tile_count=30,
            tiles_per_row=6,
        )
    )

    assert sprite_url == "/api/promking/media/onlyfans/12347/sprite.jpg"
    assert vtt_url == "/api/promking/media/onlyfans/12347/sprite.vtt"
    assert len(commands) == 1
    assert "-skip_frame" in commands[0]

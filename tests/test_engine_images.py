"""Frame-exact image-sequence export tests for :mod:`mcp_video.engine_images`.

The exactness assertions use real FFmpeg/ffprobe; the validation and
normalization tests are hermetic and only need the generated PNG fixtures.
"""

from __future__ import annotations

import json
import shutil
import struct
import subprocess
import sys
import zlib

import pytest

from mcp_video.errors import MCPVideoError
from mcp_video.models import EditResult

requires_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="FFmpeg/ffprobe not installed",
)

EXACT_RATES = [
    (24, "24/1"),
    (25, "25/1"),
    (30, "30/1"),
    (60, "60/1"),
    ("30000/1001", "30000/1001"),
]


def _write_png(path, width: int, height: int) -> str:
    """Write a minimal RGB PNG fixture without optional image dependencies."""

    def chunk(tag: bytes, data: bytes) -> bytes:
        checksum = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", checksum)

    row = b"\x00" + b"\x00\x00\x00" * width
    raw = row * height
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    payload = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")
    path.write_bytes(payload)
    return str(path)


def _probe_frames(path: str) -> tuple[int, str]:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-count_frames",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=nb_read_frames,r_frame_rate",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    stream = json.loads(result.stdout)["streams"][0]
    return int(stream["nb_read_frames"]), stream["r_frame_rate"]


@requires_ffmpeg
@pytest.mark.parametrize(("fps", "expected_rate"), EXACT_RATES)
@pytest.mark.parametrize("count", [1, 2, 90])
def test_output_has_exactly_one_frame_per_input(tmp_path, fps, expected_rate, count):
    images = [_write_png(tmp_path / f"frame_{i:04d}.png", 16, 16) for i in range(count)]
    output = str(tmp_path / "exact.mp4")

    from mcp_video.engine_images import create_from_images

    create_from_images(images, output_path=output, fps=fps)

    frames, rate = _probe_frames(output)
    assert frames == count
    assert rate == expected_rate


@requires_ffmpeg
def test_list_file_supplies_one_thousand_paths(tmp_path):
    images = [_write_png(tmp_path / f"frame_{i:04d}.png", 16, 16) for i in range(1000)]
    list_file = tmp_path / "frames.txt"
    list_file.write_text("\n\n" + "\n".join(images) + "\n\n", encoding="utf-8")
    output = str(tmp_path / "listed.mp4")

    from mcp_video.engine_images import create_from_images

    create_from_images(list_file=str(list_file), output_path=output, fps=30)

    frames, rate = _probe_frames(output)
    assert frames == 1000
    assert rate == "30/1"


def test_list_file_and_images_are_mutually_exclusive(tmp_path):
    image = _write_png(tmp_path / "frame.png", 10, 10)
    list_file = tmp_path / "frames.txt"
    list_file.write_text(image + "\n", encoding="utf-8")

    from mcp_video.engine_images import create_from_images

    with pytest.raises(MCPVideoError) as exc_info:
        create_from_images([image], list_file=str(list_file))

    assert exc_info.value.error_type == "validation_error"


def test_list_file_with_missing_image_is_rejected(tmp_path):
    list_file = tmp_path / "frames.txt"
    list_file.write_text(str(tmp_path / "missing.png") + "\n", encoding="utf-8")

    from mcp_video.engine_images import create_from_images

    with pytest.raises(MCPVideoError):
        create_from_images(list_file=str(list_file))


@pytest.mark.parametrize("fps", [0, -1, 61, "30000/0", "abc"])
def test_invalid_frame_rates_are_rejected(fps):
    from mcp_video.engine_images import create_from_images

    with pytest.raises(MCPVideoError) as exc_info:
        create_from_images(["/nonexistent/image.png"], fps=fps)

    assert exc_info.value.error_type == "validation_error"


def test_frame_rate_serialization_accepts_rationals():
    from mcp_video.engine_images import _format_fps_for_ffmpeg

    assert _format_fps_for_ffmpeg("30000/1001") == "30000/1001"
    assert _format_fps_for_ffmpeg("60/1") == "60/1"
    assert _format_fps_for_ffmpeg(30) == "30"
    assert _format_fps_for_ffmpeg(29.97002997) == "29.97002997"


def test_even_dimension_pngs_skip_normalization(tmp_path, monkeypatch):
    from mcp_video import engine_images

    image = _write_png(tmp_path / "even.png", 10, 10)
    calls = {"normalize": 0}

    def fake_normalize(images, tmpdir):
        calls["normalize"] += 1
        return images

    monkeypatch.setattr(engine_images, "_normalize_images", fake_normalize)
    monkeypatch.setattr(engine_images, "_run_ffmpeg", lambda args: None)
    monkeypatch.setattr(
        engine_images,
        "_build_edit_result",
        lambda output, operation, timing: EditResult(output_path=output, operation=operation),
    )

    engine_images.create_from_images([image], output_path=str(tmp_path / "even.mp4"), fps=30)

    assert calls["normalize"] == 0


def test_odd_dimension_pngs_are_normalized(tmp_path, monkeypatch):
    from mcp_video import engine_images

    image = _write_png(tmp_path / "odd.png", 11, 11)
    calls = {"normalize": 0}

    def fake_normalize(images, tmpdir):
        calls["normalize"] += 1
        return images

    monkeypatch.setattr(engine_images, "_normalize_images", fake_normalize)
    monkeypatch.setattr(engine_images, "_run_ffmpeg", lambda args: None)
    monkeypatch.setattr(
        engine_images,
        "_build_edit_result",
        lambda output, operation, timing: EditResult(output_path=output, operation=operation),
    )

    engine_images.create_from_images([image], output_path=str(tmp_path / "odd.mp4"), fps=30)

    assert calls["normalize"] == 1


@requires_ffmpeg
def test_positional_images_and_float_fps_still_work(tmp_path):
    images = [_write_png(tmp_path / f"frame_{i}.png", 16, 16) for i in range(2)]
    output = str(tmp_path / "legacy.mp4")

    from mcp_video.engine_images import create_from_images

    result = create_from_images(images, output, 12.0)

    assert result.output_path == output
    frames, rate = _probe_frames(output)
    assert frames == 2
    assert rate == "12/1"


def test_mcp_tool_rejects_invalid_frame_rates(tmp_path):
    from mcp_video.server_tools_advanced import video_create_from_images

    image = _write_png(tmp_path / "frame.png", 10, 10)
    for fps in (0, -1, 61, "30000/0", "abc"):
        result = video_create_from_images(images=[image], fps=fps)
        assert result["success"] is False
        assert result["error"]["type"] == "validation_error"


@requires_ffmpeg
def test_cli_rejects_invalid_frame_rate(tmp_path):
    image = _write_png(tmp_path / "frame.png", 10, 10)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "mcp_video",
            "--format",
            "json",
            "create-from-images",
            image,
            "--fps",
            "61",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )

    assert result.returncode != 0
    error = json.loads(result.stderr)["error"]
    assert error["type"] == "validation_error"


def test_cli_parser_accepts_list_file_and_rational_fps():
    from mcp_video.cli.parser import build_parser

    args = build_parser().parse_args(["create-from-images", "--list", "frames.txt", "--fps", "30000/1001"])

    assert args.inputs == []
    assert args.list_file == "frames.txt"
    assert args.fps == "30000/1001"


@requires_ffmpeg
def test_cli_list_file_export_is_frame_exact(tmp_path):
    images = [_write_png(tmp_path / f"frame_{i}.png", 16, 16) for i in range(3)]
    list_file = tmp_path / "frames.txt"
    list_file.write_text("\n".join(images) + "\n", encoding="utf-8")
    output = tmp_path / "cli.mp4"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "mcp_video",
            "--format",
            "json",
            "create-from-images",
            "--list",
            str(list_file),
            "--fps",
            "24",
            "-o",
            str(output),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["success"] is True
    frames, rate = _probe_frames(str(output))
    assert frames == 3
    assert rate == "24/1"

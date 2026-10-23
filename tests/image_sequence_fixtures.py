"""Frame-exact image-sequence export tests for :mod:`mcp_video.engine_images`.

The exactness assertions use real FFmpeg/ffprobe; the validation and
normalization tests are hermetic and only need the generated PNG fixtures.
"""

from __future__ import annotations

import contextlib
import json
import shutil
import struct
import subprocess
import zlib

import pytest


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


def _write_png(path, width: int, height: int, rgb: tuple[int, int, int] = (0, 0, 0)) -> str:
    """Write a minimal RGB PNG fixture without optional image dependencies."""

    def chunk(tag: bytes, data: bytes) -> bytes:
        checksum = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", checksum)

    row = b"\x00" + bytes(rgb) * width
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


def _frame_hashes(path: str) -> list[str]:
    """Return one decoded frame hash per output frame via framemd5."""
    result = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:v:0", "-f", "framemd5", "-"],
        capture_output=True,
        text=True,
        check=True,
        timeout=120,
    )
    rows = [line for line in result.stdout.splitlines() if line and not line.startswith("#")]
    return [row.split(",")[-1].strip() for row in rows]


def _decode_rgb_frames(path: str, width: int, height: int) -> list[bytes]:
    """Decode every output frame to raw RGB for lossless frame inspection."""
    result = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(path),
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-",
        ],
        capture_output=True,
        check=True,
        timeout=120,
    )
    frame_size = width * height * 3
    assert len(result.stdout) % frame_size == 0
    return [result.stdout[offset : offset + frame_size] for offset in range(0, len(result.stdout), frame_size)]


def _mean_rgb(frame: bytes) -> tuple[float, float, float]:
    pixels = len(frame) // 3
    return tuple(sum(frame[channel::3]) / pixels for channel in range(3))  # type: ignore[return-value]


def _color_distance(left: tuple[float, float, float], right: tuple[int, int, int]) -> float:
    return sum((left[channel] - right[channel]) ** 2 for channel in range(3))


@contextlib.contextmanager
def _unstaged_output(path):
    """Stand-in for atomic publication when FFmpeg itself is stubbed out."""
    yield path


SEQUENCE_COLORS: list[tuple[int, int, int]] = [
    (0, 0, 0),
    (255, 0, 0),
    (0, 255, 0),
    (0, 0, 255),
    (255, 255, 0),
    (255, 0, 255),
    (0, 255, 255),
    (255, 255, 255),
    (160, 80, 32),
    (32, 80, 160),
]

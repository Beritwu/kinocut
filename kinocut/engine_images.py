"""Image sequence creation operation for the FFmpeg engine."""

from __future__ import annotations

import math
import os
import re
import shutil
import struct
import tempfile

from .engine_runtime_utils import _build_edit_result, _movflags_args, _quality_args, _timed_operation
from .paths import _auto_output
from .ffmpeg_helpers import _run_ffmpeg
from .errors import InputFileError, MCPVideoError
from .ffmpeg_helpers import _validate_input_path, _validate_output_path
from .limits import MAX_EXPORT_FRAMES_FPS
from .models import EditResult

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_RATIONAL_FPS_PATTERN = re.compile(r"^\s*(\d+)\s*/\s*(\d+)\s*$")


def create_from_images(
    images: list[str] | None = None,
    output_path: str | None = None,
    fps: float | int | str = 30.0,
    *,
    list_file: str | None = None,
) -> EditResult:
    """Create a frame-exact video from a sequence of images.

    Each input image becomes exactly one output frame. ``fps`` accepts a
    positive integer, a positive decimal, or a rational string such as
    ``"30000/1001"``. When ``list_file`` is supplied, it is a UTF-8 file with
    one image path per line; blank lines are ignored.
    """
    inputs = _resolve_inputs(images, list_file)
    _, fps_arg = _coerce_fps(fps)
    validated_images = [_validate_input_path(img) for img in inputs]

    output = output_path or _auto_output(validated_images[0], "from_images")
    _validate_output_path(output)
    with _timed_operation() as timing:
        tmpdir = tempfile.mkdtemp(prefix="mcp_video_imgseq_")
        try:
            if _all_even_png(validated_images):
                extension = ".png"
                _link_image_sequence(validated_images, tmpdir)
            else:
                normalized = _normalize_images(validated_images, tmpdir)
                extension = os.path.splitext(normalized[0])[1]
            _run_ffmpeg(
                [
                    "-framerate",
                    fps_arg,
                    "-start_number",
                    "0",
                    "-i",
                    _sequence_pattern(tmpdir, extension),
                    "-c:v",
                    "libx264",
                    *_quality_args(),
                    "-frames:v",
                    str(len(validated_images)),
                    "-pix_fmt",
                    "yuv420p",
                    *_movflags_args(output),
                    output,
                ]
            )
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    return _build_edit_result(
        output,
        "create_from_images",
        timing,
    )


def _resolve_inputs(images: list[str] | None, list_file: str | None) -> list[str]:
    if list_file is not None and images:
        raise MCPVideoError(
            "Provide either images or list_file, not both",
            error_type="validation_error",
            code="conflicting_inputs",
        )
    if list_file is not None:
        images = _read_list_file(list_file)
    if not images:
        raise MCPVideoError(
            "No images provided",
            error_type="validation_error",
            code="empty_images",
        )
    return list(images)


def _read_list_file(list_file: str) -> list[str]:
    resolved = _validate_input_path(list_file)
    try:
        with open(resolved, encoding="utf-8-sig") as handle:
            return [line.strip() for line in handle if line.strip()]
    except UnicodeDecodeError as exc:
        raise InputFileError(resolved, "list file is not valid UTF-8") from exc
    except OSError as exc:
        raise InputFileError(resolved, f"Cannot read list file: {exc}") from None


def _format_fps_for_ffmpeg(fps: float | int | str) -> str:
    """Serialize FPS without rounding non-integer values before FFmpeg sees them."""
    return _coerce_fps(fps)[1]


def _coerce_fps(fps: float | int | str) -> tuple[float, str]:
    """Validate an FPS value and return its numeric and FFmpeg-serialized forms."""
    if isinstance(fps, bool):
        raise _invalid_fps(fps)
    if isinstance(fps, str):
        match = _RATIONAL_FPS_PATTERN.match(fps)
        if match:
            numerator, denominator = int(match.group(1)), int(match.group(2))
            if denominator == 0:
                raise _invalid_fps(fps)
            try:
                value = numerator / denominator
            except OverflowError as exc:
                raise _invalid_fps(fps) from exc
            divisor = math.gcd(numerator, denominator)
            rate = f"{numerator // divisor}/{denominator // divisor}"
        else:
            value = _to_float(fps)
            rate = _format_numeric_rate(value)
    else:
        value = _to_float(fps)
        rate = _format_numeric_rate(value)

    if value <= 0 or not math.isfinite(value):
        raise _invalid_fps(fps)
    if value > MAX_EXPORT_FRAMES_FPS:
        raise MCPVideoError(
            f"fps must not exceed {MAX_EXPORT_FRAMES_FPS}, got {fps}",
            error_type="validation_error",
            code="invalid_parameter",
        )
    return value, rate


def _to_float(fps: float | int | str) -> float:
    try:
        return float(fps)
    except (OverflowError, TypeError, ValueError) as exc:
        raise _invalid_fps(fps) from exc


def _invalid_fps(fps: float | int | str) -> MCPVideoError:
    return MCPVideoError(
        f"fps must be a positive finite number, got {fps}",
        error_type="validation_error",
        code="invalid_parameter",
    )


def _format_numeric_rate(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return repr(value)


def _all_even_png(images: list[str]) -> bool:
    for img in images:
        size = _png_size(img)
        if size is None or size[0] % 2 or size[1] % 2:
            return False
    return True


def _png_size(path: str) -> tuple[int, int] | None:
    """Read PNG dimensions from the file header without invoking FFmpeg."""
    try:
        with open(path, "rb") as handle:
            header = handle.read(24)
    except OSError:
        return None
    if len(header) < 24 or header[:8] != _PNG_SIGNATURE or header[12:16] != b"IHDR":
        return None
    width, height = struct.unpack(">II", header[16:24])
    if width <= 0 or height <= 0:
        return None
    return width, height


def _sequence_pattern(tmpdir: str, extension: str) -> str:
    """Return the contiguous image2 pattern consumed by FFmpeg."""
    return os.path.join(tmpdir, f"frame_%08d{extension}")


def _link_image_sequence(images: list[str], tmpdir: str) -> None:
    """Expose even-dimension PNGs as a contiguous sequence without re-encoding.

    Hard links keep the original bytes; filesystem or privilege limitations
    fall back to a copy. Symlinks are deliberately never used.
    """
    for index, image in enumerate(images):
        target = os.path.join(tmpdir, f"frame_{index:08d}.png")
        try:
            os.link(image, target)
        except OSError:
            shutil.copy2(image, target)


def _normalize_images(images: list[str], tmpdir: str) -> list[str]:
    has_png = any(img.lower().endswith(".png") for img in images)
    img_format = "png" if has_png else "jpg"
    ext = f".{img_format}"

    normalized: list[str] = []
    for i, img in enumerate(images):
        norm_path = os.path.join(tmpdir, f"frame_{i:08d}{ext}")
        if img_format == "png":
            _run_ffmpeg(
                [
                    "-y",
                    "-i",
                    img,
                    "-vf",
                    "scale=trunc(iw/2)*2:trunc(ih/2)*2",
                    "-c:v",
                    "png",
                    norm_path,
                ]
            )
        else:
            _run_ffmpeg(
                [
                    "-y",
                    "-i",
                    img,
                    "-vf",
                    "scale=trunc(iw/2)*2:trunc(ih/2)*2",
                    "-q:v",
                    "2",
                    norm_path,
                ]
            )
        normalized.append(norm_path)
    return normalized

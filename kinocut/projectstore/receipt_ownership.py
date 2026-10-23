"""Keep inode evidence for receipts created by a durable job across restarts."""

from __future__ import annotations

import contextlib
import os
import stat
from contextvars import ContextVar
from pathlib import Path

from kinocut.errors import MCPVideoError
from kinocut.ffmpeg_helpers import _OPERATION_WRITES, _validate_artifact_location

_RECEIPT: ContextVar[Path | None] = ContextVar("kinocut_durable_receipt", default=None)


def _proof(directory: Path, info: os.stat_result) -> Path:
    return directory / f"{info.st_dev}-{info.st_ino}"


@contextlib.contextmanager
def durable_receipt_ownership(path: Path):
    """Admit only a receipt with a retained hard link from its original writer.

    Reading valid-looking JSON alone never grants ownership. Immutable inode
    witnesses live in the job's private directory and also survive a killed writer.
    Older jobs without a witness fail closed rather than adopting an existing file.
    """
    _validate_artifact_location(str(path), "Receipt path")
    directory = path.parent / f".{path.name}.ownership"
    if path.exists():
        info = path.stat(follow_symlinks=False)
        witness = _proof(directory, info)
        if (
            not stat.S_ISREG(info.st_mode)
            or directory.is_symlink()
            or witness.is_symlink()
            or not witness.exists()
            or not os.path.samefile(path, witness)
        ):
            raise MCPVideoError(
                "Existing durable receipt has no job-created inode witness",
                error_type="validation_error",
                code="unsafe_path",
            )
        writes = _OPERATION_WRITES.get()
        if writes is not None:
            writes[str(path.resolve())] = (info.st_dev, info.st_ino)
    if directory.is_symlink():
        raise MCPVideoError("Receipt ownership directory is a symlink", code="unsafe_path")
    directory.mkdir(mode=0o700, exist_ok=True)
    token = _RECEIPT.set(path.resolve())
    try:
        yield
    finally:
        _RECEIPT.reset(token)


def witness_receipt_stage(final: str, staged: str) -> None:
    """Retain the owned stage inode before atomic publication can expose it."""
    target = _RECEIPT.get()
    if target is None or Path(final).resolve() != target:
        return
    from kinocut.ffmpeg_helpers import _owns_operation_output

    if not _owns_operation_output(os.path.realpath(staged)):
        raise MCPVideoError("Receipt stage ownership changed", code="unsafe_path")
    info = os.stat(staged, follow_symlinks=False)
    os.link(staged, _proof(target.parent / f".{target.name}.ownership", info), follow_symlinks=False)

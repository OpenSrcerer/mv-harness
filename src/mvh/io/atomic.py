"""Atomic file writes for Windows (PLAN §3.3): temp file in the target folder, then ``os.replace``, retried
with
backoff on PermissionError (Defender, the search indexer and a reader holding the old file all cause it).

Stdlib only.
"""

from __future__ import annotations

import os
import shutil
import time
import uuid
from pathlib import Path

__all__ = [
    "replace_retry",
    "write_bytes",
    "write_text",
    "copy_file",
    "rmtree_retry",
    "unlink_retry",
    "RETRIES",
]

RETRIES = 12


def _sleep(k: int) -> None:
    time.sleep(min(0.05 * (2**k), 2.0))


def _tmp_for(path: Path) -> Path:
    return path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp")


def replace_retry(src: Path | str, dst: Path | str, retries: int = RETRIES) -> None:
    """os.replace with exponential backoff on PermissionError (about 10 s in total)."""
    for k in range(retries):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if k == retries - 1:
                raise
            _sleep(k)


def write_bytes(path: Path | str, data: bytes) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = _tmp_for(path)
    try:
        with open(tmp, "wb") as fh:
            fh.write(data)
        replace_retry(tmp, path)
    finally:
        if tmp.exists():
            unlink_retry(tmp)
    return path


def write_text(path: Path | str, text: str) -> Path:
    """UTF-8, LF line endings exactly as given (no newline translation)."""
    return write_bytes(path, text.encode("utf-8"))


def copy_file(src: Path | str, dst: Path | str) -> Path:
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = _tmp_for(dst)
    try:
        shutil.copyfile(src, tmp)
        replace_retry(tmp, dst)
    finally:
        if tmp.exists():
            unlink_retry(tmp)
    return dst


def unlink_retry(path: Path | str, retries: int = RETRIES) -> None:
    for k in range(retries):
        try:
            Path(path).unlink()
            return
        except FileNotFoundError:
            return
        except PermissionError:
            if k == retries - 1:
                raise
            _sleep(k)


def rmtree_retry(path: Path | str, retries: int = RETRIES) -> None:
    p = Path(path)
    for k in range(retries):
        if not p.exists():
            return
        try:
            shutil.rmtree(p)
            return
        except FileNotFoundError:
            return
        except PermissionError:
            if k == retries - 1:
                raise
            _sleep(k)
        except OSError:
            if k == retries - 1:
                raise
            _sleep(k)

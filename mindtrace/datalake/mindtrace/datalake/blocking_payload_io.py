"""Blocking filesystem helpers for datalake payloads (run via :func:`asyncio.to_thread`)."""

from __future__ import annotations

from pathlib import Path


def mkdir_and_write_bytes(upload_path: Path, data: bytes) -> None:
    """Ensure parent dirs exist and write payload bytes (blocking disk I/O)."""
    upload_path.parent.mkdir(parents=True, exist_ok=True)
    upload_path.write_bytes(data)

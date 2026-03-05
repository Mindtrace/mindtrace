"""ErrorFileStore — JSONL error logs with session organisation and size-based rollover.

ErrorFileCallback — registered with track_operation's callback registry to capture
every endpoint error (type, message, full traceback, code context) to disk.

Directory layout::

    base_dir/
      sessions/
        20250304_143022_a3f7bc/   ← one folder per process lifetime
          errors_001.jsonl
          errors_002.jsonl        ← new file when previous exceeds max_file_bytes

Each JSONL line is one JSON object::

    {
      "ts": "2025-03-04T14:30:22.456+00:00",
      "session_id": "20250304_143022_a3f7bc",
      "service": "EchoService",
      "operation": "echo",
      "error_type": "RuntimeError",
      "error_message": "division by zero",
      "traceback": "Traceback (most recent call last): ...",
      "duration_ms": 12.5,
      "code_context": {
        "file": "/path/to/echo_service.py",
        "function": "echo",
        "lineno": 42,
        "snippet": "  41:     result = a\n-> 42:     return a / b\n  43:     ..."
      }
    }
"""

from __future__ import annotations

import json
import linecache
import traceback as _tb_mod
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _new_session_id() -> str:
    """Generate a session ID: YYYYMMDD_HHMMSS_<6-char hex>."""
    now = datetime.now(timezone.utc)
    return f"{now.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"


def _extract_code_context(
    exc_info: tuple,
    context_lines: int = 5,
) -> Optional[Dict[str, Any]]:
    """Return file, function, lineno, and a ±context_lines snippet from
    the innermost frame of the traceback (i.e. where the error originated).
    Returns None if no traceback is available.
    """
    _, _, tb = exc_info
    if tb is None:
        return None

    # Walk to innermost frame
    while tb.tb_next:
        tb = tb.tb_next

    frame = tb.tb_frame
    lineno = tb.tb_lineno
    filename = frame.f_code.co_filename
    func_name = frame.f_code.co_name

    lines = []
    for i in range(max(1, lineno - context_lines), lineno + context_lines + 1):
        line = linecache.getline(filename, i)
        if line:
            prefix = "->" if i == lineno else "  "
            lines.append(f"{prefix} {i:4d}: {line.rstrip()}")

    return {
        "file": filename,
        "function": func_name,
        "lineno": lineno,
        "snippet": "\n".join(lines),
    }


# ---------------------------------------------------------------------------
# ErrorFileStore
# ---------------------------------------------------------------------------


class ErrorFileStore:
    """Manages JSONL error log files with session organisation and size rollover.

    Args:
        base_dir: Root directory — session folders are created under
                  ``<base_dir>/sessions/``.
        session_id: Override auto-generated session ID (mainly for testing).
        max_file_bytes: Roll over to a new file once current file reaches
                        this size (default 10 MB).
    """

    def __init__(
        self,
        base_dir: str | Path,
        session_id: Optional[str] = None,
        max_file_bytes: int = 10 * 1024 * 1024,
    ) -> None:
        self._base = Path(base_dir) / "sessions"
        self.session_id: str = session_id or _new_session_id()
        self._max_bytes = max_file_bytes
        self._session_dir = self._base / self.session_id
        self._session_dir.mkdir(parents=True, exist_ok=True)
        self._file_index = 0
        self._current_file: Path = self._next_file()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _next_file(self) -> Path:
        self._file_index += 1
        return self._session_dir / f"errors_{self._file_index:03d}.jsonl"

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def write(self, record: Dict[str, Any]) -> None:
        """Append *record* as a JSON line; rolls over when current file is full."""
        line = json.dumps(record, default=str) + "\n"
        encoded = line.encode("utf-8")
        if (
            self._current_file.exists()
            and self._current_file.stat().st_size + len(encoded) > self._max_bytes
        ):
            self._current_file = self._next_file()
        with self._current_file.open("ab") as fh:
            fh.write(encoded)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def iter_records(
        self,
        service_name: Optional[str] = None,
        since_hours: float = 24.0,
        limit: int = 50,
        all_sessions: bool = True,
    ) -> Iterator[Dict[str, Any]]:
        """Yield matching records (newest first) up to *limit*.

        Args:
            service_name: Filter to one service (None = all).
            since_hours: Only return records within this window.
            limit: Maximum records to yield.
            all_sessions: Scan all session directories (True) or only the
                          current session (False).
        """
        cutoff = datetime.now(timezone.utc).timestamp() - since_hours * 3600

        if all_sessions and self._base.exists():
            dirs = sorted(
                (d for d in self._base.iterdir() if d.is_dir()),
                reverse=True,
            )
        else:
            dirs = [self._session_dir]

        count = 0
        for session_dir in dirs:
            for jsonl_file in sorted(session_dir.glob("errors_*.jsonl"), reverse=True):
                try:
                    with jsonl_file.open("r", encoding="utf-8") as fh:
                        raw_lines = fh.readlines()
                except Exception:
                    continue

                for raw in reversed(raw_lines):
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        rec = json.loads(raw)
                    except json.JSONDecodeError:
                        continue

                    # Time filter
                    try:
                        ts = datetime.fromisoformat(rec.get("ts", "")).timestamp()
                    except Exception:
                        ts = 0.0
                    if ts < cutoff:
                        continue

                    if service_name and rec.get("service") != service_name:
                        continue

                    yield rec
                    count += 1
                    if count >= limit:
                        return

    def list_sessions(self) -> List[Dict[str, Any]]:
        """Return metadata for all session directories, newest first."""
        sessions = []
        if not self._base.exists():
            return sessions

        for session_dir in sorted(
            (d for d in self._base.iterdir() if d.is_dir()),
            reverse=True,
        ):
            files = sorted(session_dir.glob("errors_*.jsonl"))
            total_bytes = sum(f.stat().st_size for f in files)
            total_records = 0
            for f in files:
                try:
                    with f.open("r") as fh:
                        total_records += sum(1 for line in fh if line.strip())
                except Exception:
                    pass
            sessions.append(
                {
                    "session_id": session_dir.name,
                    "files": len(files),
                    "size_kb": round(total_bytes / 1024, 1),
                    "total_errors": total_records,
                    "is_current": session_dir.name == self.session_id,
                }
            )
        return sessions


# ---------------------------------------------------------------------------
# ErrorFileCallback
# ---------------------------------------------------------------------------


class ErrorFileCallback:
    """Callable registered with ``register_error_callback`` in
    ``mindtrace.core.logging.logger``.

    Captures the full exception (type, message, traceback, code context) and
    writes one JSONL record per error to the managed ``ErrorFileStore``.

    Usage::

        from mindtrace.core.logging.logger import register_error_callback
        from mindtrace.services.monitoring.error_store import (
            ErrorFileStore, ErrorFileCallback,
        )

        store = ErrorFileStore(base_dir="~/.cache/mindtrace/monitor")
        register_error_callback(ErrorFileCallback(store))
    """

    def __init__(self, store: ErrorFileStore) -> None:
        self._store = store

    def __call__(
        self,
        *,
        service_name: Optional[str],
        operation: str,
        error_type: str,
        error_message: str,
        traceback: str,
        exc_info: tuple,
        duration_ms: float,
    ) -> None:
        code_context = _extract_code_context(exc_info)
        record: Dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "session_id": self._store.session_id,
            "service": service_name or "unknown",
            "operation": operation,
            "error_type": error_type,
            "error_message": error_message,
            "traceback": traceback,
            "duration_ms": duration_ms,
        }
        if code_context:
            record["code_context"] = code_context
        self._store.write(record)

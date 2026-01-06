"""Registry types and dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, Iterator, List, Tuple

if TYPE_CHECKING:
    pass


# ─────────────────────────────────────────────────────────────────────────────
# Backend Operation Results
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class OpResult:
    """Result of a single backend operation.

    Replaces verbose status dicts like {"status": "ok", "metadata": {...}}.

    Factory methods provide clean construction:
        OpResult.ok(name, version)
        OpResult.ok(name, version, metadata=meta)
        OpResult.error(name, version, exception)
        OpResult.skipped(name, version)
    """

    name: str
    version: str
    ok: bool
    status: str = "ok"  # ok, skipped, overwritten, error
    metadata: dict | None = None
    error: str | None = None
    message: str | None = None
    path: str | None = None

    @property
    def key(self) -> Tuple[str, str]:
        """Return (name, version) tuple for dict compatibility."""
        return (self.name, self.version)

    @property
    def is_error(self) -> bool:
        return self.status == "error"

    @property
    def is_skipped(self) -> bool:
        return self.status == "skipped"

    @property
    def is_overwritten(self) -> bool:
        return self.status == "overwritten"

    @classmethod
    def success(
        cls,
        name: str,
        version: str,
        *,
        metadata: dict | None = None,
        path: str | None = None,
        status: str = "ok",
    ) -> "OpResult":
        """Create a successful result."""
        return cls(
            name=name,
            version=version,
            ok=True,
            status=status,
            metadata=metadata,
            path=path,
        )

    @classmethod
    def error_result(
        cls,
        name: str,
        version: str,
        exception: Exception | None = None,
        *,
        error: str | None = None,
        message: str | None = None,
    ) -> "OpResult":
        """Create an error result from an exception or explicit error/message."""
        if exception is not None:
            error = type(exception).__name__
            message = str(exception)
        return cls(
            name=name,
            version=version,
            ok=False,
            status="error",
            error=error,
            message=message,
        )

    @classmethod
    def skipped(cls, name: str, version: str) -> "OpResult":
        """Create a skipped result (e.g., version already exists with on_conflict='skip')."""
        return cls(name=name, version=version, ok=True, status="skipped")

    @classmethod
    def overwritten(cls, name: str, version: str) -> "OpResult":
        """Create an overwritten result."""
        return cls(name=name, version=version, ok=True, status="overwritten")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to legacy dict format for backwards compatibility."""
        if self.is_error:
            return {"status": "error", "error": self.error, "message": self.message}
        result: Dict[str, Any] = {"status": self.status}
        if self.metadata is not None:
            result["metadata"] = self.metadata
        if self.path is not None:
            result["path"] = self.path
        return result


@dataclass
class OpResults:
    """Results of batch backend operations.

    Provides dict-like access by (name, version) key while offering
    convenient properties for filtering and error handling.

    Usage:
        results = backend.push(names, versions, paths, metadata)

        # Dict-like access
        if results[(name, version)].ok:
            print(results[(name, version)].metadata)

        # Iteration
        for result in results:
            if result.ok:
                process(result)

        # Error handling
        results.raise_on_errors()  # Raises if any errors

        # Filtering
        for result in results.successful:
            ...
        for result in results.failed:
            ...
    """

    _results: Dict[Tuple[str, str], OpResult] = field(default_factory=dict)

    def add(self, result: OpResult) -> None:
        """Add a result to the collection."""
        self._results[result.key] = result

    def __getitem__(self, key: Tuple[str, str]) -> OpResult:
        return self._results[key]

    def __contains__(self, key: Tuple[str, str]) -> bool:
        return key in self._results

    def __iter__(self) -> Iterator[OpResult]:
        return iter(self._results.values())

    def __len__(self) -> int:
        return len(self._results)

    def __bool__(self) -> bool:
        return len(self._results) > 0

    def get(self, key: Tuple[str, str], default: OpResult | None = None) -> OpResult | None:
        return self._results.get(key, default)

    def first(self) -> OpResult | None:
        """Return the first (or only) result. Useful for single-item operations."""
        if self._results:
            return next(iter(self._results.values()))
        return None

    def keys(self) -> Iterator[Tuple[str, str]]:
        return iter(self._results.keys())

    def values(self) -> Iterator[OpResult]:
        return iter(self._results.values())

    def items(self) -> Iterator[Tuple[Tuple[str, str], OpResult]]:
        return iter(self._results.items())

    @property
    def successful(self) -> List[OpResult]:
        """Results where ok=True (includes skipped/overwritten)."""
        return [r for r in self._results.values() if r.ok]

    @property
    def failed(self) -> List[OpResult]:
        """Results where ok=False."""
        return [r for r in self._results.values() if not r.ok]

    @property
    def errors(self) -> List[OpResult]:
        """Results with status='error'."""
        return [r for r in self._results.values() if r.is_error]

    @property
    def all_ok(self) -> bool:
        """True if all operations succeeded."""
        return all(r.ok for r in self._results.values())

    @property
    def any_failed(self) -> bool:
        """True if any operation failed."""
        return any(not r.ok for r in self._results.values())

    def raise_on_errors(self, message_prefix: str = "Operation failed") -> None:
        """Raise RuntimeError if any results have errors."""
        errors = self.errors
        if errors:
            error_msgs = [f"{r.name}@{r.version}: {r.error} - {r.message}" for r in errors]
            raise RuntimeError(f"{message_prefix}: {'; '.join(error_msgs)}")

    def to_dict(self) -> Dict[Tuple[str, str], Dict[str, Any]]:
        """Convert to legacy dict format for backwards compatibility."""
        return {key: result.to_dict() for key, result in self._results.items()}


# ─────────────────────────────────────────────────────────────────────────────
# Registry-Level Results (for save/load batch operations)
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class BatchResult:
    """Result of a batch operation.

    Attributes:
        results: List of results in order. None for failed items.
        errors: Dict mapping (name, version) to error info for failed items.
        succeeded: List of (name, version) tuples that succeeded.
        failed: List of (name, version) tuples that failed.
    """

    results: List[Any] = field(default_factory=list)
    errors: Dict[Tuple[str, str], Dict[str, str]] = field(default_factory=dict)
    succeeded: List[Tuple[str, str]] = field(default_factory=list)
    failed: List[Tuple[str, str]] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.results)

    def __getitem__(self, index: int) -> Any:
        return self.results[index]

    def __iter__(self):
        return iter(self.results)

    @property
    def all_succeeded(self) -> bool:
        """Returns True if all items succeeded."""
        return len(self.failed) == 0

    @property
    def success_count(self) -> int:
        """Number of successful items."""
        return len(self.succeeded)

    @property
    def failure_count(self) -> int:
        """Number of failed items."""
        return len(self.failed)

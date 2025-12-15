"""Registry types and dataclasses."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple


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

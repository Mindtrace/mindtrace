from dataclasses import dataclass, field
from typing import Any, Dict, List
import numpy as np


@dataclass
class Feature:
    """Represents a detected feature with its properties."""
    id: str
    type: str
    bbox: Any
    expected: int
    found: int
    params: Dict[str, Any] = field(default_factory=dict)
    classification: str | None = None

    @property
    def is_present(self) -> bool:
        return self.found == self.expected

    @property
    def status(self) -> str:
        if not self.is_present:
            return "Missing"
        return self.classification or "Present"


@dataclass
class FeatureConfig:
    """Configuration for a feature to be detected."""
    bbox: Any
    num_expected: int = 1
    type: str = "unknown"
    params: Dict[str, Any] = field(default_factory=dict)

   



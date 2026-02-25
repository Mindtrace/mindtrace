"""ModelCard and EvalResult — structured model metadata.

:class:`ModelCard` is intended to be saved alongside model weights in the
registry so that every artifact carries a human-readable, machine-queryable
description of its provenance, performance, and intended use.

:class:`EvalResult` represents a single evaluation measurement attached to a
card.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mindtrace.models.lifecycle.stages import ModelStage


@dataclass
class EvalResult:
    """Single evaluation result entry.

    Attributes:
        metric: Name of the evaluation metric (e.g. ``"val/iou"``).
        value: Numeric value produced by the evaluation.
        dataset: Registry key or description of the evaluation dataset.
        split: Dataset split evaluated against (e.g. ``"val"``, ``"test"``).
        timestamp: UTC timestamp at which the result was recorded.
    """

    metric: str
    value: float
    dataset: str = ""
    split: str = "val"
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe plain dict.

        Returns:
            Dictionary representation with ``timestamp`` as an ISO-8601 string.
        """
        return {
            "metric": self.metric,
            "value": self.value,
            "dataset": self.dataset,
            "split": self.split,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvalResult:
        """Deserialize from a plain dict.

        Args:
            data: Dict previously produced by :meth:`to_dict`.

        Returns:
            A reconstructed :class:`EvalResult` instance.
        """
        return cls(
            metric=data["metric"],
            value=float(data["value"]),
            dataset=data.get("dataset", ""),
            split=data.get("split", "val"),
            timestamp=datetime.fromisoformat(data["timestamp"])
            if "timestamp" in data
            else datetime.now(timezone.utc),
        )


@dataclass
class ModelCard:
    """Structured metadata for a trained model.

    Intended to be saved alongside model weights in the registry so that
    every artifact carries a human-readable, machine-queryable description
    of its provenance, performance, and intended use.

    Attributes:
        name: Model identifier matching the registry key (e.g. ``"sfz-segmenter"``).
        version: Semantic version string (e.g. ``"v3"``).
        stage: Current lifecycle stage.
        task: ML task type (e.g. ``"classification"``, ``"detection"``,
            ``"segmentation"``).
        architecture: Model architecture description
            (e.g. ``"DINOv2-B + LinearHead"``).
        framework: Framework used (e.g. ``"pytorch"``, ``"huggingface"``,
            ``"ultralytics"``).
        training_data: Registry key or description of the training dataset.
        eval_results: List of :class:`EvalResult` entries in chronological
            insertion order.
        known_limitations: List of known failure modes or limitations.
        description: Human-readable description of the model and its purpose.
        created_at: Creation timestamp (UTC).
        extra: Arbitrary additional metadata that does not fit the structured
            fields above.
    """

    name: str
    version: str
    stage: ModelStage = ModelStage.DEV
    task: str = ""
    architecture: str = ""
    framework: str = "pytorch"
    training_data: str = ""
    eval_results: list[EvalResult] = field(default_factory=list)
    known_limitations: list[str] = field(default_factory=list)
    description: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    extra: dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Eval result helpers
    # ------------------------------------------------------------------

    def get_metric(self, metric: str, dataset: str = "") -> float | None:
        """Return the most recent value for a given metric name.

        When ``dataset`` is provided, only results whose ``dataset`` field
        matches are considered.

        Args:
            metric: Metric name to look up (e.g. ``"val/iou"``).
            dataset: Optional dataset filter.  When non-empty, only results
                with a matching ``dataset`` field are considered.

        Returns:
            The most recently added matching :class:`EvalResult` value, or
            ``None`` if no matching result exists.

        Example:
            >>> card.get_metric("val/iou")
            0.87
            >>> card.get_metric("val/iou", dataset="coco-val")
            0.85
        """
        candidates = [
            r for r in self.eval_results
            if r.metric == metric and (not dataset or r.dataset == dataset)
        ]
        if not candidates:
            return None
        # Return the value of the last inserted (most recent) entry.
        return candidates[-1].value

    def add_result(
        self,
        metric: str,
        value: float,
        dataset: str = "",
        split: str = "val",
    ) -> None:
        """Append an :class:`EvalResult` entry.

        Args:
            metric: Name of the evaluation metric.
            value: Numeric result value.
            dataset: Registry key or description of the evaluation dataset.
            split: Dataset split (e.g. ``"val"``, ``"test"``).

        Example:
            >>> card.add_result("val/iou", 0.87, dataset="coco-val")
        """
        self.eval_results.append(
            EvalResult(
                metric=metric,
                value=value,
                dataset=dataset,
                split=split,
            )
        )

    def summary(self) -> dict[str, float]:
        """Return a mapping of metric name to its latest recorded value.

        When the same metric appears multiple times, only the last recorded
        value is retained.

        Returns:
            ``{metric_name: latest_value}`` for all tracked metrics.

        Example:
            >>> card.summary()
            {'val/iou': 0.87, 'val/f1': 0.79}
        """
        result: dict[str, float] = {}
        for entry in self.eval_results:
            result[entry.metric] = entry.value
        return result

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe plain dict.

        All nested objects are recursively converted; :class:`datetime` values
        are represented as ISO-8601 strings and :class:`ModelStage` as its
        string value.

        Returns:
            A JSON-serialisable dictionary representation of this card.
        """
        return {
            "name": self.name,
            "version": self.version,
            "stage": self.stage.value,
            "task": self.task,
            "architecture": self.architecture,
            "framework": self.framework,
            "training_data": self.training_data,
            "eval_results": [r.to_dict() for r in self.eval_results],
            "known_limitations": list(self.known_limitations),
            "description": self.description,
            "created_at": self.created_at.isoformat(),
            "extra": dict(self.extra),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ModelCard:
        """Deserialize from a plain dict.

        Args:
            data: Dict previously produced by :meth:`to_dict` or compatible
                JSON payload.

        Returns:
            A reconstructed :class:`ModelCard` instance.

        Raises:
            KeyError: If required fields ``name`` or ``version`` are absent.
            ValueError: If the ``stage`` value is not a valid
                :class:`ModelStage`.
        """
        eval_results = [
            EvalResult.from_dict(r) for r in data.get("eval_results", [])
        ]
        created_at_raw = data.get("created_at")
        created_at = (
            datetime.fromisoformat(created_at_raw)
            if created_at_raw
            else datetime.now(timezone.utc)
        )
        return cls(
            name=data["name"],
            version=data["version"],
            stage=ModelStage(data.get("stage", ModelStage.DEV.value)),
            task=data.get("task", ""),
            architecture=data.get("architecture", ""),
            framework=data.get("framework", "pytorch"),
            training_data=data.get("training_data", ""),
            eval_results=eval_results,
            known_limitations=list(data.get("known_limitations", [])),
            description=data.get("description", ""),
            created_at=created_at,
            extra=dict(data.get("extra", {})),
        )

    def save(self, path: str | Path) -> None:
        """Save the card as a JSON file.

        Parent directories are created automatically if they do not exist.

        Args:
            path: Destination file path.  The file will be UTF-8 encoded with
                two-space indentation for human readability.

        Raises:
            OSError: If the file cannot be written.

        Example:
            >>> card.save("/tmp/sfz-segmenter-v3.json")
        """
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: str | Path) -> ModelCard:
        """Load a card from a JSON file.

        Args:
            path: Path to a JSON file previously written by :meth:`save`.

        Returns:
            A reconstructed :class:`ModelCard` instance.

        Raises:
            FileNotFoundError: If the file does not exist.
            json.JSONDecodeError: If the file is not valid JSON.
            KeyError: If required fields are missing from the JSON payload.

        Example:
            >>> card = ModelCard.load("/tmp/sfz-segmenter-v3.json")
        """
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(data)

    # ------------------------------------------------------------------
    # Registry key helpers
    # ------------------------------------------------------------------

    def registry_key(self, stage: ModelStage | None = None) -> str:
        """Return the registry key for this card.

        The base key format is ``"{name}:{version}"``.  When ``stage`` is
        provided the key is extended to ``"{name}:{version}:{stage.value}"``.

        Args:
            stage: Optional stage suffix.  If ``None``, the stage is omitted.

        Returns:
            A registry key string suitable for use with
            :class:`mindtrace.registry.Registry`.

        Example:
            >>> card.registry_key()
            'sfz-segmenter:v3'
            >>> card.registry_key(ModelStage.PRODUCTION)
            'sfz-segmenter:v3:production'
        """
        base = f"{self.name}:{self.version}"
        if stage is not None:
            return f"{base}:{stage.value}"
        return base

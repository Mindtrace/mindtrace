"""ModelCard — the lifecycle handle for a trained model.

A :class:`ModelCard` ties together a model's weights in the registry, its
evaluation metrics, and its lifecycle stage.  All lifecycle operations
(save, load, promote, demote) go through the card, ensuring the model
artifact and its metadata are always consistent.

Example::

    from mindtrace.models.lifecycle import ModelCard, ModelStage
    from mindtrace.registry import Registry

    registry = Registry("/tmp/my_registry")

    card = ModelCard(
        name="image-classifier",
        version="v1",
        task="classification",
        registry=registry,
    )

    # Save model weights through the card
    card.save_model(trained_model)

    # Record evaluation metrics
    card.add_result("val/accuracy", 0.94)
    card.add_result("val/f1", 0.93)

    # Promote with metric gates
    card.promote(to_stage=ModelStage.STAGING, require={"val/accuracy": 0.85})

    # Load the model back
    model = card.load_model()
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from mindtrace.core import utcnow
from mindtrace.models.lifecycle.stages import (
    VALID_DEMOTIONS,
    VALID_PROMOTIONS,
    ModelStage,
)

logger = logging.getLogger(__name__)


@dataclass
class EvalResult:
    """Single evaluation result entry.

    Attributes:
        metric: Name of the evaluation metric (e.g. ``"val/accuracy"``).
        value: Numeric value produced by the evaluation.
        dataset: Registry key or description of the evaluation dataset.
        split: Dataset split evaluated against (e.g. ``"val"``, ``"test"``).
        timestamp: UTC timestamp at which the result was recorded.
    """

    metric: str
    value: float
    dataset: str = ""
    split: str = "val"
    timestamp: datetime = field(default_factory=utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "value": self.value,
            "dataset": self.dataset,
            "split": self.split,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvalResult:
        return cls(
            metric=data["metric"],
            value=float(data["value"]),
            dataset=data.get("dataset", ""),
            split=data.get("split", "val"),
            timestamp=(datetime.fromisoformat(data["timestamp"]) if "timestamp" in data else utcnow()),
        )


class PromotionError(Exception):
    """Raised when a promotion or demotion transition is invalid or fails."""


@dataclass
class PromotionResult:
    """Outcome of a promote or demote operation.

    Attributes:
        success: Whether the operation completed.
        from_stage: Stage before the operation.
        to_stage: Requested target stage.
        model_name: Name of the model.
        model_version: Version of the model.
        failed_requirements: ``{metric: (actual, required)}`` for failed gates.
        timestamp: When the operation was evaluated.
    """

    success: bool
    from_stage: ModelStage
    to_stage: ModelStage
    model_name: str
    model_version: str
    failed_requirements: dict[str, tuple[float, float]] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=utcnow)


@dataclass
class ModelVariant:
    """A per-target build of a model (e.g. an edge-optimized artifact).

    Variants track alternate deployable forms of the same logical model —
    a quantized ONNX export, a pruned OpenVINO build, etc. — each with its
    own artifact reference, optimization recipe, metrics, and lifecycle
    stage that is promoted independently of the parent card.

    Attributes:
        name: Variant identifier, typically the target name (e.g. ``"cpu-int8"``).
        artifact: Path or registry key of the compiled/exported artifact.
        recipe_json: JSON-encoded optimization recipe that produced the artifact.
        stage: Lifecycle stage of this variant.
        metrics: Flat ``{metric: value}`` map (benchmark metrics use a
            ``"bench/"`` prefix).
        created_at: ISO-format UTC timestamp at which the variant was recorded.
    """

    name: str
    artifact: str = ""
    recipe_json: str = ""
    stage: ModelStage = ModelStage.DEV
    metrics: dict[str, float] = field(default_factory=dict)
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict."""
        return {
            "name": self.name,
            "artifact": self.artifact,
            "recipe_json": self.recipe_json,
            "stage": self.stage.value,
            "metrics": dict(self.metrics),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ModelVariant:
        """Deserialize from a dict."""
        return cls(
            name=data["name"],
            artifact=data.get("artifact", ""),
            recipe_json=data.get("recipe_json", ""),
            stage=ModelStage(data.get("stage", ModelStage.DEV.value)),
            metrics={k: float(v) for k, v in data.get("metrics", {}).items()},
            created_at=data.get("created_at", ""),
        )


@dataclass
class ModelCard:
    """Lifecycle handle for a trained model.

    Ties together model weights, evaluation metrics, and lifecycle stage.
    When ``registry`` is provided, all operations (save, load, promote,
    demote) are persisted to the registry automatically.

    Attributes:
        name: Model identifier (e.g. ``"image-classifier"``).
        version: Version string (e.g. ``"v1"``).
        registry: A ``mindtrace.registry.Registry`` instance for persistence.
        stage: Current lifecycle stage.
        task: ML task type (e.g. ``"classification"``).
        architecture: Architecture description (e.g. ``"ResNet50 + LinearHead"``).
        framework: Framework used (default ``"pytorch"``).
        training_data: Description of the training dataset.
        eval_results: Evaluation metrics in insertion order.
        variants: Per-target builds of this model, keyed by variant name.
        known_limitations: Known failure modes or limitations.
        description: Human-readable description.
        created_at: Creation timestamp (UTC).
        extra: Arbitrary additional metadata.
    """

    name: str
    version: str
    registry: Any = field(default=None, repr=False)
    stage: ModelStage = ModelStage.DEV
    task: str = ""
    architecture: str = ""
    framework: str = "pytorch"
    training_data: str = ""
    eval_results: list[EvalResult] = field(default_factory=list)
    known_limitations: list[str] = field(default_factory=list)
    description: str = ""
    created_at: datetime = field(default_factory=utcnow)
    extra: dict[str, Any] = field(default_factory=dict)
    variants: dict[str, ModelVariant] = field(default_factory=dict)
    _model_saved: bool = field(default=False, init=False, repr=False)

    # ------------------------------------------------------------------
    # Registry key
    # ------------------------------------------------------------------

    def registry_key(self, stage: ModelStage | None = None) -> str:
        """Return the registry key for this model.

        Args:
            stage: Optional stage suffix.

        Returns:
            ``"name:version"`` or ``"name:version:stage"`` when stage is given.
        """
        base = f"{self.name}:{self.version}"
        if stage is not None:
            return f"{base}:{stage.value}"
        return base

    # ------------------------------------------------------------------
    # Model save / load
    # ------------------------------------------------------------------

    def save_model(self, model: Any) -> str:
        """Save model weights to the registry.

        Uses ``registry.save(name, model, version=version)`` so that
        the registry manages name and version separately.

        Args:
            model: The model object (e.g. ``nn.Module``) to persist.

        Returns:
            The registry key under which the model was saved.

        Raises:
            RuntimeError: If no registry is attached to this card.
        """
        self._require_registry("save_model")
        self.registry.save(self.name, model, version=self.version)
        self._model_saved = True
        logger.info("ModelCard: saved model weights as '%s'.", self.registry_key())
        return self.registry_key()

    def load_model(self) -> Any:
        """Load model weights from the registry.

        Returns:
            The deserialized model object.

        Raises:
            RuntimeError: If no registry is attached to this card.
        """
        self._require_registry("load_model")
        model = self.registry.load(self.name, version=self.version)
        logger.info("ModelCard: loaded model from '%s'.", self.registry_key())
        return model

    @property
    def model_exists(self) -> bool:
        """Check whether the model artifact exists in the registry."""
        if self.registry is None:
            return False
        try:
            return self.registry.has_object(self.name, self.version)
        except Exception:
            return self._model_saved

    # ------------------------------------------------------------------
    # Eval results
    # ------------------------------------------------------------------

    def add_result(
        self,
        metric: str,
        value: float,
        dataset: str = "",
        split: str = "val",
    ) -> None:
        """Record an evaluation metric."""
        self.eval_results.append(EvalResult(metric=metric, value=value, dataset=dataset, split=split))

    def get_metric(self, metric: str, dataset: str = "") -> float | None:
        """Return the most recent value for a metric, or None."""
        candidates = [r for r in self.eval_results if r.metric == metric and (not dataset or r.dataset == dataset)]
        return candidates[-1].value if candidates else None

    def summary(self) -> dict[str, float]:
        """Return ``{metric: latest_value}`` for all tracked metrics."""
        result: dict[str, float] = {}
        for entry in self.eval_results:
            result[entry.metric] = entry.value
        return result

    # ------------------------------------------------------------------
    # Variants
    # ------------------------------------------------------------------

    def add_variant(
        self,
        name: str,
        *,
        artifact: str = "",
        recipe_json: str = "",
        metrics: dict[str, float] | None = None,
        report: Any = None,
    ) -> ModelVariant:
        """Record a per-target variant of this model.

        Args:
            name: Variant identifier (e.g. ``"cpu-int8"``).
            artifact: Path or registry key of the compiled/exported artifact.
            recipe_json: JSON-encoded optimization recipe.
            metrics: Initial ``{metric: value}`` entries.
            report: Optional ``BenchmarkReport``-like object exposing
                ``to_dict()``; its numeric entries are merged into the
                variant metrics under a ``"bench/"`` prefix.

        Returns:
            The newly registered :class:`ModelVariant`.
        """
        merged: dict[str, float] = dict(metrics or {})
        if report is not None:
            for key, value in report.to_dict().items():
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    continue
                merged[f"bench/{key}"] = float(value)
        variant = ModelVariant(
            name=name,
            artifact=artifact,
            recipe_json=recipe_json,
            metrics=merged,
            created_at=utcnow().isoformat(),
        )
        self.variants[name] = variant
        logger.info("ModelCard: added variant '%s' to %s:%s.", name, self.name, self.version)
        return variant

    def get_variant(self, name: str) -> ModelVariant:
        """Return a registered variant by name.

        Args:
            name: Variant identifier.

        Returns:
            The matching :class:`ModelVariant`.

        Raises:
            KeyError: If no such variant exists; the message lists the
                available variant names.
        """
        try:
            return self.variants[name]
        except KeyError:
            available = sorted(self.variants)
            raise KeyError(
                f"Unknown variant {name!r} for {self.name}:{self.version}. Available: {available}."
            ) from None

    def promote_variant(
        self,
        name: str,
        *,
        to_stage: ModelStage,
        require: dict[str, float] | None = None,
        dry_run: bool = False,
    ) -> PromotionResult:
        """Promote a variant to a new lifecycle stage, gated on its metrics.

        Gate semantics per requirement key: keys ending in ``"_max"``
        (e.g. ``"bench/p95_ms_max"``) pass when the variant metric named by
        the key without the suffix is ``<=`` the threshold; all other keys
        pass when the metric is ``>=`` the threshold. Unlike
        :meth:`promote`, failed gates do not raise — they are reported via
        ``PromotionResult(success=False, failed_requirements=...)``.

        Args:
            name: Variant identifier.
            to_stage: Target stage.
            require: ``{metric_or_metric_max: threshold}`` gates.
            dry_run: Evaluate gates without applying the stage change.

        Returns:
            :class:`PromotionResult` describing the outcome.

        Raises:
            KeyError: If the variant does not exist.
            PromotionError: If the stage transition is invalid.
        """
        variant = self.get_variant(name)
        from_stage = variant.stage

        if not from_stage.can_promote_to(to_stage):
            allowed = sorted(s.value for s in VALID_PROMOTIONS.get(from_stage, set()))
            raise PromotionError(
                f"Invalid promotion for variant {name!r}: {from_stage.value!r} -> {to_stage.value!r}. "
                f"Allowed: {allowed}."
            )

        failures = self._evaluate_gates(variant.metrics.get, require) if require else {}
        result = PromotionResult(
            success=len(failures) == 0,
            from_stage=from_stage,
            to_stage=to_stage,
            model_name=f"{self.name}/{name}",
            model_version=self.version,
            failed_requirements=failures,
        )

        if failures or dry_run:
            return result

        variant.stage = to_stage
        if self.registry is not None:
            try:
                self.persist()
            except Exception:
                variant.stage = from_stage
                raise
        logger.info(
            "Promoted variant %s of %s:%s from %s to %s.",
            name,
            self.name,
            self.version,
            from_stage.value,
            to_stage.value,
        )
        return result

    def demote_variant(
        self,
        name: str,
        *,
        to_stage: ModelStage,
        reason: str = "",
    ) -> PromotionResult:
        """Demote a variant to an earlier or archival stage.

        Args:
            name: Variant identifier.
            to_stage: Target stage.
            reason: Human-readable reason for demotion.

        Returns:
            :class:`PromotionResult` describing the outcome.

        Raises:
            KeyError: If the variant does not exist.
            PromotionError: If the stage transition is invalid.
        """
        variant = self.get_variant(name)
        from_stage = variant.stage

        if not from_stage.can_demote_to(to_stage):
            allowed = sorted(s.value for s in VALID_DEMOTIONS.get(from_stage, set()))
            raise PromotionError(
                f"Invalid demotion for variant {name!r}: {from_stage.value!r} -> {to_stage.value!r}. "
                f"Allowed: {allowed}."
            )

        if reason:
            self.extra[f"demotion_reason/{name}"] = reason

        variant.stage = to_stage
        if self.registry is not None:
            try:
                self.persist()
            except Exception:
                variant.stage = from_stage
                raise
        logger.info(
            "Demoted variant %s of %s:%s from %s to %s.%s",
            name,
            self.name,
            self.version,
            from_stage.value,
            to_stage.value,
            f" Reason: {reason}" if reason else "",
        )
        return PromotionResult(
            success=True,
            from_stage=from_stage,
            to_stage=to_stage,
            model_name=f"{self.name}/{name}",
            model_version=self.version,
        )

    # ------------------------------------------------------------------
    # Lifecycle: promote / demote
    # ------------------------------------------------------------------

    def promote(
        self,
        *,
        to_stage: ModelStage,
        require: dict[str, float] | None = None,
        dry_run: bool = False,
    ) -> PromotionResult:
        """Promote this model to a new lifecycle stage.

        Validates the transition against ``VALID_PROMOTIONS``, checks metric
        gates, persists the card to the registry, then updates the stage.
        The stage is only updated after a successful persist.

        Args:
            to_stage: Target stage.
            require: ``{metric: minimum_value}`` thresholds.
            dry_run: Validate without applying changes.

        Returns:
            :class:`PromotionResult` describing the outcome.

        Raises:
            PromotionError: If the transition is invalid or metrics fail.
            RuntimeError: If no registry is attached.
        """
        self._require_registry("promote")
        from_stage = self.stage

        if not from_stage.can_promote_to(to_stage):
            allowed = sorted(s.value for s in VALID_PROMOTIONS.get(from_stage, set()))
            raise PromotionError(f"Invalid promotion: {from_stage.value!r} -> {to_stage.value!r}. Allowed: {allowed}.")

        failures = self._check_requirements(require) if require else {}

        result = PromotionResult(
            success=len(failures) == 0,
            from_stage=from_stage,
            to_stage=to_stage,
            model_name=self.name,
            model_version=self.version,
            failed_requirements=failures,
        )

        if failures and not dry_run:
            details = "; ".join(
                f"{m}: actual={'missing' if math.isnan(a) else f'{a:.4g}'}, required={r:.4g}"
                for m, (a, r) in failures.items()
            )
            raise PromotionError(f"Promotion of {self.name}:{self.version} to {to_stage.value!r} blocked: {details}")

        if dry_run:
            return result

        # Persist BEFORE updating stage -- if persist fails, stage stays unchanged.
        old_stage = self.stage
        self.stage = to_stage
        try:
            self.persist()
        except Exception:
            self.stage = old_stage
            raise

        logger.info(
            "Promoted %s:%s from %s to %s.",
            self.name,
            self.version,
            from_stage.value,
            to_stage.value,
        )
        return result

    def demote(
        self,
        *,
        to_stage: ModelStage,
        reason: str = "",
        dry_run: bool = False,
    ) -> PromotionResult:
        """Demote this model to an earlier or archival stage.

        Validates the transition against ``VALID_DEMOTIONS``. Unlike
        :meth:`promote`, demotion does not check metric thresholds.

        Args:
            to_stage: Target stage.
            reason: Human-readable reason for demotion.
            dry_run: Validate without applying changes.

        Returns:
            :class:`PromotionResult` describing the outcome.

        Raises:
            PromotionError: If the transition is invalid.
            RuntimeError: If no registry is attached.
        """
        self._require_registry("demote")
        from_stage = self.stage

        if not from_stage.can_demote_to(to_stage):
            allowed = sorted(s.value for s in VALID_DEMOTIONS.get(from_stage, set()))
            raise PromotionError(f"Invalid demotion: {from_stage.value!r} -> {to_stage.value!r}. Allowed: {allowed}.")

        result = PromotionResult(
            success=True,
            from_stage=from_stage,
            to_stage=to_stage,
            model_name=self.name,
            model_version=self.version,
        )

        if dry_run:
            return result

        if reason:
            self.extra["demotion_reason"] = reason

        # Persist BEFORE updating stage.
        old_stage = self.stage
        self.stage = to_stage
        try:
            self.persist()
        except Exception:
            self.stage = old_stage
            raise

        log_msg = "Demoted %s:%s from %s to %s."
        log_args: list[Any] = [
            self.name,
            self.version,
            from_stage.value,
            to_stage.value,
        ]
        if reason:
            log_msg += " Reason: %s"
            log_args.append(reason)
        logger.info(log_msg, *log_args)
        return result

    # ------------------------------------------------------------------
    # Card persistence
    # ------------------------------------------------------------------

    def persist(self) -> None:
        """Save the card metadata to the registry.

        Raises:
            RuntimeError: If no registry is attached.
        """
        self._require_registry("persist")
        key = f"{self.registry_key()}:card:{self.stage.value}"
        self.registry.save(key, self.to_dict())
        logger.info("ModelCard: persisted metadata as '%s'.", key)

    @classmethod
    def from_registry(
        cls,
        registry: Any,
        name: str,
        version: str,
        stage: ModelStage = ModelStage.DEV,
    ) -> ModelCard:
        """Load a card from the registry.

        Args:
            registry: A ``mindtrace.registry.Registry`` instance.
            name: Model name.
            version: Model version.
            stage: Stage of the card to load (default DEV).

        Returns:
            Reconstructed :class:`ModelCard` with the registry attached.
        """
        key = f"{name}:{version}:card:{stage.value}"
        data = registry.load(key)
        card = cls.from_dict(data)
        card.registry = registry
        card._model_saved = True
        return card

    # ------------------------------------------------------------------
    # JSON serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict."""
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
            "variants": {name: variant.to_dict() for name, variant in self.variants.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ModelCard:
        """Deserialize from a dict."""
        eval_results = [EvalResult.from_dict(r) for r in data.get("eval_results", [])]
        created_at_raw = data.get("created_at")
        created_at = datetime.fromisoformat(created_at_raw) if created_at_raw else utcnow()
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
            variants={name: ModelVariant.from_dict(v) for name, v in data.get("variants", {}).items()},
        )

    def save_json(self, path: str | Path) -> None:
        """Save the card as a JSON file."""
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    @classmethod
    def load_json(cls, path: str | Path) -> ModelCard:
        """Load a card from a JSON file."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(data)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require_registry(self, operation: str) -> None:
        if self.registry is None:
            raise RuntimeError(f"ModelCard.{operation}() requires a registry. Pass registry= when creating the card.")

    def _check_requirements(self, require: dict[str, float]) -> dict[str, tuple[float, float]]:
        return self._evaluate_gates(self.get_metric, require)

    @staticmethod
    def _evaluate_gates(
        lookup: Callable[[str], float | None],
        require: dict[str, float],
    ) -> dict[str, tuple[float, float]]:
        """Evaluate metric gates against a metric lookup function.

        Keys ending in ``"_max"`` are upper-bound gates: the metric named by
        the key without the suffix must be ``<=`` the threshold. All other
        keys are lower-bound gates: the metric must be ``>=`` the threshold.
        Missing metrics fail with an actual value of NaN.

        Args:
            lookup: Callable returning the metric value or None if missing.
            require: ``{metric_or_metric_max: threshold}`` gates.

        Returns:
            ``{requirement_key: (actual, required)}`` for failed gates.
        """
        failures: dict[str, tuple[float, float]] = {}
        for key, threshold in require.items():
            is_max = key.endswith("_max")
            actual = lookup(key[: -len("_max")] if is_max else key)
            if actual is None:
                failures[key] = (float("nan"), threshold)
            elif (actual > threshold) if is_max else (actual < threshold):
                failures[key] = (actual, threshold)
        return failures

"""TrainingApp: scheduled / trigger-based training with datalake + registry integration.

Wraps mindtrace-automation TrainingPipeline into an application that can be
triggered on-demand, on a schedule (via mindtrace-jobs), or by a threshold
(e.g., "N new labeled samples arrived in the datalake").
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from mindtrace.core import Mindtrace

try:
    from mindtrace.automation.pipeline.training import TrainingConfig, TrainingPipeline  # noqa: F401

    _AUTOMATION_AVAILABLE = True
except ImportError:
    _AUTOMATION_AVAILABLE = False


@dataclass
class TrainingAppConfig:
    """Configuration for TrainingApp."""

    app_name: str = "training_app"
    training_config: Any = None  # TrainingConfig instance
    min_new_samples: int = 0  # trigger only when this many new samples exist
    new_samples_query: dict = field(default_factory=dict)  # datalake query to count new samples
    auto_push_to_registry: bool = True
    metadata: dict = field(default_factory=dict)


class TrainingApp(Mindtrace):
    """On-demand or threshold-triggered training application.

    Example::

        app = TrainingApp(
            trainer=classification_trainer,
            evaluator=evaluator,
            registry=registry,
            config=TrainingAppConfig(
                app_name="weld_classifier_training",
                training_config=TrainingConfig(
                    model_name="weld_classifier",
                    version="v3",
                    promote_on_improvement=True,
                    min_accuracy_gain=0.005,
                ),
                min_new_samples=200,
            ),
            datalake=datalake,
        )
        result = app.run()
    """

    def __init__(
        self,
        trainer: Any,
        config: TrainingAppConfig | None = None,
        evaluator: Any | None = None,
        registry: Any | None = None,
        datalake: Any | None = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.trainer = trainer
        self.config = config or TrainingAppConfig()
        self.evaluator = evaluator
        self.registry = registry
        self.datalake = datalake

    def _count_new_samples(self) -> int:
        """Query datalake for new labeled samples count."""
        if self.datalake is None or not self.config.new_samples_query:
            return 0
        try:
            rows = asyncio.run(self.datalake.query_data(self.config.new_samples_query, datums_wanted=None))
            return len(rows)
        except Exception as exc:
            self.logger.warning(f"Could not count new samples: {exc}")
            return 0

    def should_train(self) -> bool:
        """Return True if training should be triggered."""
        if self.config.min_new_samples <= 0:
            return True
        count = self._count_new_samples()
        self.logger.info(f"New samples: {count} / {self.config.min_new_samples} required")
        return count >= self.config.min_new_samples

    def run(self) -> Any:
        """Run the training pipeline if the trigger condition is met.

        Returns:
            PipelineResult if training ran, or None if threshold not met.
        """
        if not _AUTOMATION_AVAILABLE:
            raise RuntimeError("mindtrace-automation is required for TrainingApp")

        self.logger.info(f"TrainingApp '{self.config.app_name}' checking trigger...")
        if not self.should_train():
            self.logger.info("Trigger condition not met — skipping training.")
            return None

        training_config = self.config.training_config
        if training_config is None:
            raise ValueError("TrainingAppConfig.training_config must be set")

        pipeline = TrainingPipeline.build(
            name=f"{self.config.app_name}_pipeline",
            trainer=self.trainer,
            config=training_config,
            evaluator=self.evaluator,
            registry=self.registry if self.config.auto_push_to_registry else None,
        )
        self.logger.info(f"Starting training pipeline '{pipeline.name}'...")
        result = pipeline.run()
        self.logger.info(f"Training {'succeeded' if result.success else 'FAILED'} in {result.total_duration_s:.1f}s")
        return result

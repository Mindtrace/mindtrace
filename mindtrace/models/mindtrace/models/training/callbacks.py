"""Training callbacks for the MindTrace ML platform.

This module defines the abstract ``Callback`` base class and a set of concrete
callback implementations that integrate with the ``Trainer`` training loop.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from mindtrace.core import Mindtrace
from mindtrace.models.lifecycle.card import ModelCard

if TYPE_CHECKING:
    from mindtrace.models.training.trainer import Trainer


class Callback(Mindtrace):
    """Base class for all training callbacks.

    Subclasses override the hook methods they care about. All hooks receive
    a reference to the active ``Trainer`` instance so they can inspect or
    mutate training state (e.g. set ``trainer.stop_training = True``).

    Inherits from :class:`~mindtrace.core.Mindtrace` to provide unified
    logging via ``self.logger`` and configuration via ``self.config``.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def on_train_begin(self, trainer: Trainer) -> None:
        """Called once before the first epoch starts.

        Args:
            trainer: The active ``Trainer`` instance.
        """

    def on_train_end(self, trainer: Trainer) -> None:
        """Called once after the last epoch finishes (or early stopping).

        Args:
            trainer: The active ``Trainer`` instance.
        """

    def on_epoch_begin(self, trainer: Trainer, epoch: int) -> None:
        """Called at the start of each epoch.

        Args:
            trainer: The active ``Trainer`` instance.
            epoch: Zero-based epoch index.
        """

    def on_epoch_end(self, trainer: Trainer, epoch: int, logs: dict[str, float]) -> None:
        """Called at the end of each epoch.

        Args:
            trainer: The active ``Trainer`` instance.
            epoch: Zero-based epoch index.
            logs: Mapping of metric names to their epoch-averaged values.
        """

    def on_batch_begin(self, trainer: Trainer, batch: int) -> None:
        """Called at the start of each training batch.

        Args:
            trainer: The active ``Trainer`` instance.
            batch: Zero-based batch index within the current epoch.
        """

    def on_batch_end(self, trainer: Trainer, batch: int, loss: float) -> None:
        """Called at the end of each training batch.

        Args:
            trainer: The active ``Trainer`` instance.
            batch: Zero-based batch index within the current epoch.
            loss: The scalar loss value for this batch.
        """


class ModelCheckpoint(Callback):
    """Saves the model to a registry whenever a monitored metric improves.

    The checkpoint key written to the registry is formatted as
    ``"{model_name}:{version_prefix}{epoch}"``.

    Attributes:
        best_value: Best observed value of the monitored metric so far.
        last_saved_key: The registry key of the most recently saved checkpoint.

    Example::

        checkpoint = ModelCheckpoint(
            registry=registry,
            monitor="val/loss",
            mode="min",
            save_best_only=True,
            model_name="resnet50",
            version_prefix="v",
        )
        trainer.fit(train_loader, val_loader, epochs=10, callbacks=[checkpoint])
    """

    def __init__(
        self,
        registry: Any,
        monitor: str = "val/loss",
        mode: str = "min",
        save_best_only: bool = True,
        model_name: str = "checkpoint",
        version_prefix: str = "v",
        raise_on_save_failure: bool = False,
        task: str = "",
    ) -> None:
        """Initialise the checkpoint callback.

        Args:
            registry: A ``Registry`` instance exposing a ``save(name, obj)``
                method.
            monitor: Name of the metric to monitor (must appear in the
                ``logs`` dict passed to ``on_epoch_end``).
            mode: ``"min"`` if lower is better (e.g. loss), ``"max"`` if
                higher is better (e.g. accuracy, IoU).
            save_best_only: When ``True`` only saves when the metric improves.
                When ``False`` saves every epoch regardless.
            model_name: Base name used when constructing the registry key.
            version_prefix: String prepended to the epoch number in the
                registry key (e.g. ``"v"`` → ``"resnet50:v3"``).
            raise_on_save_failure: When ``True``, re-raise save exceptions
                instead of silently swallowing them.  Defaults to ``False``
                for backward compatibility.

        Raises:
            ValueError: If *mode* is not ``"min"`` or ``"max"``.
        """
        if mode not in ("min", "max"):
            raise ValueError(f"mode must be 'min' or 'max', got '{mode}'")

        super().__init__()

        self.registry = registry
        self.monitor = monitor
        self.mode = mode
        self.save_best_only = save_best_only
        self.model_name = model_name
        self.version_prefix = version_prefix
        self.raise_on_save_failure = raise_on_save_failure
        self.task = task

        self.best_value: float = math.inf if mode == "min" else -math.inf
        self.last_saved_key: str | None = None
        self.card: ModelCard | None = None
        self.save_failures: int = 0
        self.last_error: Exception | None = None

    def _is_improvement(self, current: float) -> bool:
        """Return ``True`` if *current* is better than ``self.best_value``."""
        if self.mode == "min":
            return current < self.best_value
        return current > self.best_value

    def on_epoch_end(self, trainer: Trainer, epoch: int, logs: dict[str, float]) -> None:
        """Conditionally save the model based on the monitored metric.

        Args:
            trainer: The active ``Trainer`` instance; ``trainer.model`` is
                the object passed to ``registry.save``.
            epoch: Zero-based epoch index used to construct the registry key.
            logs: Metric dict from the completed epoch.
        """
        current = logs.get(self.monitor)
        if current is None:
            self.logger.warning(
                "ModelCheckpoint: monitored metric '%s' not found in logs %s. Skipping checkpoint.",
                self.monitor,
                list(logs.keys()),
            )
            return

        improved = self._is_improvement(current)

        if self.save_best_only and not improved:
            return

        if improved:
            self.best_value = current

        version = f"{self.version_prefix}{epoch}"
        card = ModelCard(
            name=self.model_name,
            version=version,
            task=self.task,
            registry=self.registry,
        )
        for metric_name, metric_value in logs.items():
            if isinstance(metric_value, (int, float)):
                card.add_result(metric_name, float(metric_value))

        try:
            card.save_model(trainer.model)
            self.last_saved_key = card.registry_key()
            self.card = card
            self.logger.info(
                "ModelCheckpoint: saved '%s' (epoch=%d, %s=%.6f).",
                card.registry_key(),
                epoch,
                self.monitor,
                current,
            )
        except Exception as exc:
            self.save_failures += 1
            self.last_error = exc
            self.logger.error(
                "ModelCheckpoint: failed to save '%s' (%d total failure%s): %s",
                card.registry_key(),
                self.save_failures,
                "s" if self.save_failures > 1 else "",
                exc,
                exc_info=True,
            )
            if self.raise_on_save_failure:
                raise


class EarlyStopping(Callback):
    """Stops training when a monitored metric stops improving.

    After ``patience`` epochs without improvement the callback sets
    ``trainer.stop_training = True``, which causes the ``Trainer.fit`` loop
    to exit after completing the current epoch.

    Attributes:
        best_value: Best observed value of the monitored metric so far.
        wait: Number of consecutive epochs without improvement.
        stopped_epoch: The epoch at which training was stopped, or ``-1`` if
            training completed normally.

    Example::

        early_stop = EarlyStopping(monitor="val/loss", patience=5, mode="min")
        trainer.fit(train_loader, val_loader, epochs=100, callbacks=[early_stop])
    """

    def __init__(
        self,
        monitor: str = "val/loss",
        patience: int = 10,
        mode: str = "min",
        min_delta: float = 1e-4,
    ) -> None:
        """Initialise early stopping.

        Args:
            monitor: Metric name to monitor (must appear in epoch logs).
            patience: Number of epochs with no improvement before stopping.
            mode: ``"min"`` if lower is better, ``"max"`` if higher is better.
            min_delta: Minimum change in the monitored quantity to qualify as
                an improvement.

        Raises:
            ValueError: If *mode* is not ``"min"`` or ``"max"``.
        """
        if mode not in ("min", "max"):
            raise ValueError(f"mode must be 'min' or 'max', got '{mode}'")

        super().__init__()

        self.monitor = monitor
        self.patience = patience
        self.mode = mode
        self.min_delta = min_delta

        self.best_value: float = math.inf if mode == "min" else -math.inf
        self.wait: int = 0
        self.stopped_epoch: int = -1

    def _is_improvement(self, current: float) -> bool:
        """Return ``True`` if *current* exceeds the threshold for improvement."""
        if self.mode == "min":
            return current < self.best_value - self.min_delta
        return current > self.best_value + self.min_delta

    def on_train_begin(self, trainer: Trainer) -> None:
        """Reset internal state at the start of a training run.

        Args:
            trainer: The active ``Trainer`` instance.
        """
        self.best_value = math.inf if self.mode == "min" else -math.inf
        self.wait = 0
        self.stopped_epoch = -1

    def on_epoch_end(self, trainer: Trainer, epoch: int, logs: dict[str, float]) -> None:
        """Check for improvement and potentially stop training.

        Args:
            trainer: The active ``Trainer`` instance.
            epoch: Zero-based epoch index.
            logs: Metric dict from the completed epoch.
        """
        current = logs.get(self.monitor)
        if current is None:
            self.logger.warning(
                "EarlyStopping: monitored metric '%s' not found in logs %s.",
                self.monitor,
                list(logs.keys()),
            )
            return

        if self._is_improvement(current):
            self.best_value = current
            self.wait = 0
        else:
            self.wait += 1
            if self.wait >= self.patience:
                self.stopped_epoch = epoch
                trainer.stop_training = True
                self.logger.info(
                    "EarlyStopping: stopping at epoch %d. No improvement in '%s' for %d epochs (best=%.6f).",
                    epoch,
                    self.monitor,
                    self.patience,
                    self.best_value,
                )


class LRMonitor(Callback):
    """Logs the current learning rate each epoch.

    When a tracker is supplied the LR is also forwarded via
    ``tracker.log({"train/lr": lr}, step=epoch)``.

    Example::

        lr_monitor = LRMonitor(tracker=wandb_tracker)
        trainer.fit(train_loader, epochs=50, callbacks=[lr_monitor])
    """

    def __init__(self, tracker: Any | None = None) -> None:
        """Initialise the LR monitor.

        Args:
            tracker: An optional tracker instance (e.g. a
                ``mindtrace.models.tracking.Tracker``) with a
                ``log(metrics, step)`` method.  If ``None`` only Python
                logging is used.
        """
        super().__init__()
        self.tracker = tracker

    def on_epoch_end(self, trainer: Trainer, epoch: int, logs: dict[str, float]) -> None:
        """Read and log the learning rate for the completed epoch.

        Args:
            trainer: The active ``Trainer`` instance; ``trainer.optimizer``
                must expose ``param_groups``.
            epoch: Zero-based epoch index used as the step value when logging
                to the tracker.
            logs: Metric dict (not modified by this callback).
        """
        try:
            lr: float = trainer.optimizer.param_groups[0]["lr"]
        except (AttributeError, IndexError, KeyError) as exc:
            self.logger.warning("LRMonitor: could not read learning rate: %s", exc)
            return

        self.logger.debug("LRMonitor: epoch=%d lr=%.2e", epoch, lr)

        if self.tracker is not None:
            try:
                self.tracker.log({"train/lr": lr}, step=epoch)
            except Exception as exc:
                self.logger.warning("LRMonitor: tracker.log failed: %s", exc)


class UnfreezeSchedule(Callback):
    """Progressively unfreeze model parameters at specified epochs.

    Designed for fine-tuning workflows where the backbone starts frozen and
    layers are gradually unfrozen as training progresses.

    Args:
        schedule: Dict mapping zero-based epoch index to a list of parameter
            name prefixes to unfreeze at that epoch.  Every parameter whose
            ``name`` starts with any prefix in the list will have
            ``requires_grad`` set to ``True``.

            Example — unfreeze the last two ResNet stages at epoch 5 and the
            full backbone at epoch 10::

                schedule = {
                    5:  ["backbone.layer3", "backbone.layer4"],
                    10: ["backbone"],
                }

        new_lr: Optional learning rate to assign to newly unfrozen parameters
            via an extra optimizer param group.  When ``None`` the existing
            optimizer LR is used for those parameters.

    Example::

        unfreeze = UnfreezeSchedule(
            schedule={5: ["backbone.layer3", "backbone.layer4"], 10: ["backbone"]},
            new_lr=5e-5,
        )
        trainer.fit(train_loader, epochs=15, callbacks=[unfreeze])
    """

    def __init__(
        self,
        schedule: dict[int, list[str]],
        new_lr: float | None = None,
    ) -> None:
        super().__init__()
        self.schedule = schedule
        self.new_lr = new_lr

    def on_epoch_begin(self, trainer: Trainer, epoch: int) -> None:
        """Unfreeze parameters listed for the current epoch.

        Args:
            trainer: The active ``Trainer`` instance.
            epoch: Zero-based epoch index.
        """
        prefixes = self.schedule.get(epoch)
        if not prefixes:
            return

        unfrozen_params: list[Any] = []
        unfrozen_names: list[str] = []

        for name, param in trainer.model.named_parameters():
            if any(name.startswith(pfx) for pfx in prefixes):
                if not param.requires_grad:
                    param.requires_grad_(True)
                    unfrozen_params.append(param)
                    unfrozen_names.append(name)

        if not unfrozen_params:
            self.logger.warning(
                "UnfreezeSchedule: epoch %d — no frozen parameters matched prefixes %s. "
                "Check for typos in your prefix names.",
                epoch,
                prefixes,
            )
            return

        self.logger.info(
            "UnfreezeSchedule: epoch %d — unfroze %d parameter tensor(s) matching %s.",
            epoch,
            len(unfrozen_params),
            prefixes,
        )

        if self.new_lr is not None:
            try:
                trainer.optimizer.add_param_group({"params": unfrozen_params, "lr": self.new_lr})
                self.logger.info(
                    "UnfreezeSchedule: added new param group with lr=%.2e for unfrozen params.",
                    self.new_lr,
                )
            except Exception as exc:
                self.logger.warning("UnfreezeSchedule: could not add param group: %s", exc)


class OptunaCallback(Callback):
    """Optuna-aware callback for hyperparameter search.

    Reports intermediate metric values to an Optuna trial after each epoch
    and raises ``optuna.TrialPruned`` when the pruner decides to stop the
    trial early.

    **Duck-typed** — no hard Optuna dependency.  Pass any object that
    implements ``.report(value: float, step: int)`` and
    ``.should_prune() -> bool``.

    Args:
        trial: Optuna trial object (or any duck-typed equivalent).
        monitor: Metric name to report.  Must appear in the ``logs`` dict
            passed to ``on_epoch_end``.  Defaults to ``"val/loss"``.

    Example::

        import optuna
        from mindtrace.models.training import OptunaCallback

        def objective(trial):
            lr = trial.suggest_float("lr", 1e-5, 1e-2, log=True)
            model = build_model("resnet50", "linear", num_classes=3)
            optimizer = build_optimizer("adamw", model, lr=lr)
            trainer = Trainer(
                model=model,
                loss_fn=nn.CrossEntropyLoss(),
                optimizer=optimizer,
                callbacks=[OptunaCallback(trial, monitor="val/loss")],
            )
            trainer.fit(train_loader, val_loader, epochs=20)
            return trainer.history["val/loss"][-1]

        study = optuna.create_study(direction="minimize")
        study.optimize(objective, n_trials=50)
    """

    def __init__(self, trial: Any, monitor: str = "val/loss") -> None:
        super().__init__()
        self.trial = trial
        self.monitor = monitor

    def on_epoch_end(self, trainer: Trainer, epoch: int, logs: dict[str, float]) -> None:
        """Report the monitored metric and prune if necessary.

        Args:
            trainer: The active ``Trainer`` instance.
            epoch: Zero-based epoch index (used as the step for Optuna).
            logs: Metric dict from the completed epoch.
        """
        value = logs.get(self.monitor)
        if value is None:
            self.logger.warning(
                "OptunaCallback: monitored metric '%s' not in logs %s — skipping report.",
                self.monitor,
                list(logs.keys()),
            )
            return

        try:
            self.trial.report(float(value), step=epoch)
        except Exception as exc:
            self.logger.warning("OptunaCallback: trial.report() failed: %s", exc)
            return

        try:
            should_prune = self.trial.should_prune()
        except Exception as exc:
            self.logger.warning("OptunaCallback: trial.should_prune() failed: %s", exc)
            return

        if should_prune:
            trainer.stop_training = True
            self.logger.info(
                "OptunaCallback: trial pruned at epoch %d (%s=%.6f).",
                epoch,
                self.monitor,
                value,
            )
            # Raise TrialPruned if Optuna is available so it is recorded correctly.
            try:
                import optuna  # noqa: PLC0415

                raise optuna.TrialPruned()
            except ImportError:
                pass


class ProgressLogger(Callback):
    """Logs a human-readable epoch summary at INFO level.

    Example output::

        Epoch 3/20 — train/loss=0.4321  val/loss=0.5678  val/acc=0.8901

    Example::

        progress = ProgressLogger()
        trainer.fit(train_loader, val_loader, epochs=20, callbacks=[progress])
    """

    def __init__(self) -> None:
        """Initialise the progress logger, storing total epochs once known."""
        super().__init__()
        self._total_epochs: int = 0

    def on_train_begin(self, trainer: Trainer) -> None:
        """Cache the total number of epochs for display purposes.

        Args:
            trainer: The active ``Trainer`` instance.
        """
        self._total_epochs = getattr(trainer, "_total_epochs", 0)

    def on_epoch_end(self, trainer: Trainer, epoch: int, logs: dict[str, float]) -> None:
        """Emit an INFO-level summary of the completed epoch.

        Args:
            trainer: The active ``Trainer`` instance.
            epoch: Zero-based epoch index.
            logs: Metric dict from the completed epoch.
        """
        total = self._total_epochs or "?"
        # Build a sorted metric string for consistent, readable output.
        metrics_str = "  ".join(f"{k}={v:.4f}" for k, v in sorted(logs.items()))
        self.logger.info("Epoch %d/%s — %s", epoch + 1, total, metrics_str)

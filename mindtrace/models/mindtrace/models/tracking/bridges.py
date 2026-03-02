"""Tracker bridges for third-party training frameworks.

Provides adapter classes that bridge the callback/logging systems of external
training frameworks (Ultralytics YOLO, HuggingFace Transformers) to the
mindtrace :class:`~mindtrace.models.tracking.tracker.Tracker` interface.

Usage::

    from mindtrace.models.tracking import Tracker
    from mindtrace.models.tracking.bridges import UltralyticsTrackerBridge

    tracker = Tracker.from_config("mlflow", tracking_uri="http://localhost:5000")
    bridge = UltralyticsTrackerBridge(tracker)
    bridge.attach(yolo_model)
    yolo_model.train(data="dataset.yaml", epochs=50)
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class UltralyticsTrackerBridge:
    """Bridges Ultralytics YOLO callbacks to a mindtrace Tracker.

    Registers ``on_fit_epoch_end`` and ``on_train_end`` callbacks on a YOLO
    model instance so that training metrics are forwarded to the tracker
    automatically.

    Args:
        tracker: A mindtrace ``Tracker`` instance.  When ``None`` the bridge
            is a no-op (metrics are still logged via Python logging).
    """

    EPOCH_METRIC_KEYS: tuple[str, ...] = (
        "train/box_loss",
        "train/cls_loss",
        "train/dfl_loss",
        "metrics/precision(B)",
        "metrics/recall(B)",
        "metrics/mAP50(B)",
        "metrics/mAP50-95(B)",
        "val/box_loss",
        "val/cls_loss",
        "val/dfl_loss",
    )

    def __init__(self, tracker: Any | None = None) -> None:
        self._tracker = tracker
        self._current_epoch: int = 0

    @property
    def current_epoch(self) -> int:
        return self._current_epoch

    def attach(self, model: Any) -> None:
        """Register Ultralytics callbacks on *model*.

        Args:
            model: An ``ultralytics.YOLO`` instance about to be trained.
        """
        bridge = self

        def _on_fit_epoch_end(ultralytics_trainer: Any) -> None:
            epoch: int = getattr(ultralytics_trainer, "epoch", bridge._current_epoch)
            bridge._current_epoch = epoch

            raw_metrics: dict = getattr(ultralytics_trainer, "metrics", {})
            loggable: dict[str, float] = {}
            for key in bridge.EPOCH_METRIC_KEYS:
                if key in raw_metrics:
                    val = raw_metrics[key]
                    if isinstance(val, (int, float)):
                        loggable[key] = float(val)

            for key, val in raw_metrics.items():
                if key not in loggable and isinstance(val, (int, float)):
                    loggable[key] = float(val)

            logger.debug("UltralyticsTrackerBridge: epoch=%d metrics=%s", epoch, loggable)

            if bridge._tracker is not None and loggable:
                try:
                    bridge._tracker.log(loggable, step=epoch)
                except Exception as exc:
                    logger.warning(
                        "UltralyticsTrackerBridge: tracker.log failed at epoch %d: %s",
                        epoch,
                        exc,
                    )

        def _on_train_end(ultralytics_trainer: Any) -> None:
            raw_metrics: dict = getattr(ultralytics_trainer, "metrics", {})
            final_loggable: dict[str, float] = {
                k: float(v)
                for k, v in raw_metrics.items()
                if isinstance(v, (int, float))
            }
            logger.info(
                "UltralyticsTrackerBridge: training ended — final metrics: %s",
                final_loggable,
            )
            if bridge._tracker is not None and final_loggable:
                try:
                    bridge._tracker.log(
                        {f"final/{k}": v for k, v in final_loggable.items()},
                        step=bridge._current_epoch,
                    )
                except Exception as exc:
                    logger.warning(
                        "UltralyticsTrackerBridge: tracker.log (on_train_end) failed: %s",
                        exc,
                    )

        model.add_callback("on_fit_epoch_end", _on_fit_epoch_end)
        model.add_callback("on_train_end", _on_train_end)
        logger.debug("UltralyticsTrackerBridge: callbacks registered on YOLO model.")


class HuggingFaceTrackerBridge:
    """Bridges HuggingFace Trainer callbacks to a mindtrace Tracker.

    This class duck-types the HuggingFace ``TrainerCallback`` interface.  When
    ``transformers`` is available it additionally inherits from
    ``TrainerCallback`` so that the HF Trainer accepts it natively.

    Usage::

        bridge = HuggingFaceTrackerBridge(tracker)
        hf_trainer = HFTrainer(..., callbacks=[bridge])

    Args:
        tracker: A mindtrace ``Tracker`` instance.
    """

    def __init__(self, tracker: Any | None = None) -> None:
        self._tracker = tracker

    def on_log(
        self,
        args: Any,
        state: Any,
        control: Any,
        logs: dict[str, float] | None = None,
        **kwargs: Any,
    ) -> None:
        """Forward HuggingFace training logs to the mindtrace tracker."""
        if logs is None or self._tracker is None:
            return

        step: int = getattr(state, "global_step", 0)
        loggable = {k: float(v) for k, v in logs.items() if isinstance(v, (int, float))}

        if not loggable:
            return

        logger.debug("HuggingFaceTrackerBridge: step=%d metrics=%s", step, loggable)

        try:
            self._tracker.log(loggable, step=step)
        except Exception as exc:
            logger.warning(
                "HuggingFaceTrackerBridge: tracker.log failed at step %d: %s",
                step,
                exc,
            )


# When transformers is available, create a subclass that also inherits from
# TrainerCallback so the HF Trainer accepts it without type errors.
try:
    from transformers import TrainerCallback as _TrainerCallback

    class _HFBridgeWithCallback(_TrainerCallback, HuggingFaceTrackerBridge):
        """HuggingFaceTrackerBridge that inherits from TrainerCallback."""

        def __init__(self, tracker: Any | None = None) -> None:
            _TrainerCallback.__init__(self)
            HuggingFaceTrackerBridge.__init__(self, tracker)

    # Replace the public class so users get the TrainerCallback-compatible version.
    HuggingFaceTrackerBridge = _HFBridgeWithCallback  # type: ignore[misc]
except ImportError:
    pass

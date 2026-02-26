"""Core training loop for the MindTrace ML platform.

The ``Trainer`` class orchestrates the full supervised training workflow:
model forward passes, loss computation, gradient accumulation, mixed-precision
training, LR scheduling, callback dispatch, and metric history tracking.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

import torch
import torch.nn as nn
from torch.optim import Optimizer
from torch.optim.lr_scheduler import LRScheduler, ReduceLROnPlateau

from mindtrace.models.training.callbacks import Callback

logger = logging.getLogger(__name__)


class Trainer:
    """Supervised training loop with mixed precision and callback support.

    The ``Trainer`` is deliberately framework-agnostic at the data level: it
    accepts any iterable ``DataLoader``-like object.  Batch unpacking is
    controlled by ``batch_fn`` so callers can handle unusual batch layouts
    without subclassing.

    Attributes:
        model: The ``nn.Module`` being trained.
        loss_fn: Loss callable (``nn.Module`` or plain function).
        optimizer: The PyTorch optimizer.
        scheduler: Optional LR scheduler.
        tracker: Optional experiment tracker (duck-typed).
        callbacks: Ordered list of active ``Callback`` instances.
        device: Resolved ``torch.device`` used for training.
        mixed_precision: Whether AMP is active.
        gradient_accumulation_steps: Number of micro-batches before an
            optimizer step.
        clip_grad_norm: Maximum gradient norm for clipping, or ``None``.
        batch_fn: Callable that maps a raw batch to ``(inputs, targets)``.
        stop_training: Set to ``True`` by callbacks (e.g. ``EarlyStopping``)
            to terminate the fit loop after the current epoch.
        history: Dict mapping metric names to per-epoch value lists.

    Example::

        trainer = Trainer(
            model=model,
            loss_fn=nn.CrossEntropyLoss(),
            optimizer=build_optimizer("adamw", model, lr=3e-4),
            scheduler=build_scheduler("cosine", optimizer, total_steps=5000),
            mixed_precision=True,
            gradient_accumulation_steps=4,
            clip_grad_norm=1.0,
        )
        history = trainer.fit(train_loader, val_loader, epochs=20)
    """

    def __init__(
        self,
        model: nn.Module,
        loss_fn: nn.Module | Callable,
        optimizer: Optimizer,
        *,
        train_loader: Any | None = None,
        val_loader: Any | None = None,
        scheduler: LRScheduler | None = None,
        tracker: Any | None = None,
        callbacks: list[Callback] | None = None,
        device: str = "auto",
        mixed_precision: bool = False,
        gradient_accumulation_steps: int = 1,
        clip_grad_norm: float | None = None,
        batch_fn: Callable | None = None,
        gradient_checkpointing: bool = False,
        ddp: bool = False,
    ) -> None:
        """Initialise the trainer.

        Args:
            model: PyTorch module to train.
            loss_fn: Loss function. Called as ``loss_fn(outputs, targets)``.
            optimizer: Optimizer that updates ``model`` parameters.
            train_loader: Optional default training data loader.  Stored and
                used by :meth:`train` and as a fallback by :meth:`fit` when
                the *train_loader* argument is ``None``.
            val_loader: Optional default validation data loader.  Stored and
                used by :meth:`train` and as a fallback by :meth:`fit` when
                the *val_loader* argument is ``None``.
            scheduler: Optional LR scheduler. ``ReduceLROnPlateau`` is
                stepped after validation; all others after each optimizer step.
            tracker: Optional experiment-tracking object (e.g. a
                ``mindtrace.models.tracking.Tracker``) with a
                ``log(metrics, step)`` interface.
            callbacks: List of ``Callback`` instances invoked during training.
            device: Device string.  ``"auto"`` selects CUDA if available,
                otherwise CPU.
            mixed_precision: Enable ``torch.amp`` automatic mixed precision.
                Silently ignored when CUDA is not available.
            gradient_accumulation_steps: Accumulate gradients over this many
                batches before calling ``optimizer.step()``.  Must be >= 1.
            clip_grad_norm: If set, clips the global gradient norm to this
                value before each optimizer step.
            batch_fn: Optional callable ``(batch) -> (inputs, targets)``.
                When ``None`` the trainer falls back to tuple unpacking.
            gradient_checkpointing: Enable gradient checkpointing to trade
                compute for memory.  Calls
                ``model.gradient_checkpointing_enable()`` when the model
                supports it (e.g. HuggingFace transformers models).  Silently
                ignored when the model does not expose that method.
            ddp: Wrap the model in
                :class:`~torch.nn.parallel.DistributedDataParallel` for
                multi-GPU training.  Uses ``mindtrace.cluster.distributed``
                when available; falls back to native PyTorch DDP.  Has no
                effect when no distributed process group is initialised or
                when world size is 1.

        Raises:
            ValueError: If *gradient_accumulation_steps* < 1.
        """
        if gradient_accumulation_steps < 1:
            raise ValueError(
                f"gradient_accumulation_steps must be >= 1, "
                f"got {gradient_accumulation_steps}"
            )

        self.model = model
        self.loss_fn = loss_fn
        self.optimizer = optimizer
        self.scheduler = scheduler
        self.tracker = tracker
        self.callbacks: list[Callback] = callbacks or []
        self.mixed_precision = mixed_precision
        self.gradient_accumulation_steps = gradient_accumulation_steps
        self.clip_grad_norm = clip_grad_norm
        self.batch_fn = batch_fn
        self._ddp = ddp
        self._default_train_loader = train_loader
        self._default_val_loader = val_loader

        # Device resolution
        if device == "auto":
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        else:
            self.device = torch.device(device)

        # AMP setup — only activate when CUDA is actually available
        self._amp_enabled: bool = (
            mixed_precision
            and self.device.type == "cuda"
            and torch.cuda.is_available()
        )

        if mixed_precision and not self._amp_enabled:
            logger.warning(
                "Trainer: mixed_precision=True but CUDA is not available. "
                "Running in full precision."
            )

        self._scaler: torch.amp.GradScaler | None = (
            torch.amp.GradScaler() if self._amp_enabled else None
        )

        # Mutable training state
        self.stop_training: bool = False
        self.history: dict[str, list[float]] = {}
        self._total_epochs: int = 0

        self.model.to(self.device)

        # Gradient checkpointing — reduces VRAM at the cost of recomputation
        if gradient_checkpointing:
            if hasattr(self.model, "gradient_checkpointing_enable"):
                self.model.gradient_checkpointing_enable()
                logger.info("Trainer: gradient checkpointing enabled.")
            else:
                logger.warning(
                    "Trainer: gradient_checkpointing=True but model has no "
                    "gradient_checkpointing_enable() method — ignored."
                )

        # DDP wrapping — prefer mindtrace.cluster, fall back to native torch
        if ddp:
            try:
                from mindtrace.cluster.distributed import wrap_ddp as _wrap_ddp  # noqa: PLC0415
                self.model = _wrap_ddp(self.model)
            except ImportError:
                try:
                    import torch.distributed as _dist  # noqa: PLC0415
                    if _dist.is_initialized() and _dist.get_world_size() > 1:
                        from torch.nn.parallel import DistributedDataParallel as _DDP  # noqa: PLC0415
                        _device_ids = (
                            [self.device.index]
                            if self.device.type == "cuda" and self.device.index is not None
                            else None
                        )
                        self.model = _DDP(self.model, device_ids=_device_ids)
                        logger.info("Trainer: wrapped model in DistributedDataParallel.")
                    else:
                        logger.debug(
                            "Trainer: ddp=True but no distributed process group active "
                            "— running single-process."
                        )
                except ImportError:
                    logger.debug("Trainer: ddp=True but torch.distributed unavailable.")

        logger.info(
            "Trainer initialised — device=%s, amp=%s, grad_accum=%d, "
            "grad_ckpt=%s, ddp=%s",
            self.device,
            self._amp_enabled,
            self.gradient_accumulation_steps,
            gradient_checkpointing,
            ddp,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def train(self, **kwargs: Any) -> dict[str, float]:
        """Train the model and return flat (last-epoch) metrics.

        This is the interface expected by
        :class:`~mindtrace.automation.pipeline.training.TrainingPipeline`.
        It delegates to :meth:`fit` using the loaders stored at construction
        time (overridable via *kwargs*) and flattens the per-epoch history
        to a single dict of final-epoch values.

        Keyword Args:
            train_loader: Override the default training loader.
            val_loader: Override the default validation loader.
            epochs: Number of epochs (default ``1``).

        Returns:
            Dict mapping metric names to their **last-epoch** scalar values.

        Raises:
            ValueError: If no *train_loader* is available (neither passed
                here nor at init time).
        """
        train_loader = kwargs.pop("train_loader", self._default_train_loader)
        val_loader = kwargs.pop("val_loader", self._default_val_loader)
        epochs = kwargs.pop("epochs", 1)

        if train_loader is None:
            raise ValueError(
                "Trainer.train(): train_loader is required — pass it at "
                "init time or as a keyword argument."
            )

        history = self.fit(train_loader, val_loader, epochs=epochs)
        return {k: v[-1] for k, v in history.items()}

    def fit(
        self,
        train_loader: Any | None = None,
        val_loader: Any | None = None,
        epochs: int = 1,
    ) -> dict[str, list[float]]:
        """Run the full training loop.

        Args:
            train_loader: Iterable providing training batches.
            val_loader: Optional iterable providing validation batches. When
                ``None`` validation is skipped.
            epochs: Total number of epochs to train for.

        Returns:
            ``history``: a dict mapping metric names (e.g. ``"train/loss"``,
            ``"val/loss"``) to lists of per-epoch scalar values.
        """
        # Fall back to default loaders when None is passed
        if train_loader is None:
            train_loader = self._default_train_loader
        if val_loader is None:
            val_loader = self._default_val_loader

        if train_loader is None:
            raise ValueError(
                "Trainer.fit(): train_loader is required — pass it directly "
                "or set it at init time."
            )

        self._total_epochs = epochs
        self.stop_training = False
        self.history = {}

        self._call_callbacks("on_train_begin")

        for epoch in range(epochs):
            self._call_callbacks("on_epoch_begin", epoch=epoch)

            train_metrics = self._train_epoch(train_loader)
            logs: dict[str, float] = {**train_metrics}

            if val_loader is not None:
                val_metrics = self._val_epoch(val_loader)
                logs.update(val_metrics)

                # ReduceLROnPlateau is stepped against the validation loss
                if isinstance(self.scheduler, ReduceLROnPlateau):
                    val_loss = val_metrics.get("val/loss")
                    if val_loss is not None:
                        self.scheduler.step(val_loss)

            # Accumulate history
            for metric, value in logs.items():
                self.history.setdefault(metric, []).append(value)

            # Log to tracker if provided
            if self.tracker is not None:
                try:
                    self.tracker.log(logs, step=epoch)
                except Exception as exc:
                    logger.warning("Trainer: tracker.log failed at epoch %d: %s", epoch, exc)

            self._call_callbacks("on_epoch_end", epoch=epoch, logs=logs)

            if self.stop_training:
                logger.info("Trainer: early stopping triggered at epoch %d.", epoch)
                break

        self._call_callbacks("on_train_end")
        return self.history

    # ------------------------------------------------------------------
    # Internal epoch helpers
    # ------------------------------------------------------------------

    def _train_epoch(self, loader: Any) -> dict[str, float]:
        """Execute one full training epoch.

        Handles gradient accumulation and optional mixed-precision forward
        passes.  The optimizer is stepped every
        ``gradient_accumulation_steps`` batches (and always on the final
        batch of the epoch to avoid discarding a partial accumulation window).

        Args:
            loader: Iterable of training batches.

        Returns:
            Dict with a single key ``"train/loss"`` mapped to the mean batch
            loss over the epoch.
        """
        self.model.train()

        total_loss = 0.0
        num_batches = 0

        self.optimizer.zero_grad()

        for batch_idx, raw_batch in enumerate(loader):
            self._call_callbacks("on_batch_begin", batch=batch_idx)

            inputs, targets = self._unpack_batch(raw_batch)
            inputs = self._to_device(inputs)
            targets = self._to_device(targets)

            # Forward + loss
            if self._amp_enabled and self._scaler is not None:
                with torch.amp.autocast(device_type=self.device.type):
                    outputs = self.model(inputs)
                    loss: torch.Tensor = self.loss_fn(outputs, targets)
            else:
                outputs = self.model(inputs)
                loss = self.loss_fn(outputs, targets)

            # Scale loss for accumulation so gradients average correctly
            scaled_loss = loss / self.gradient_accumulation_steps

            if self._amp_enabled and self._scaler is not None:
                self._scaler.scale(scaled_loss).backward()
            else:
                scaled_loss.backward()

            is_accumulation_step = (
                (batch_idx + 1) % self.gradient_accumulation_steps == 0
            )
            # Check if this is the last batch (handle partial windows at epoch end)
            try:
                is_last_batch = batch_idx == len(loader) - 1  # type: ignore[arg-type]
            except TypeError:
                # Loader doesn't support len()
                is_last_batch = False

            if is_accumulation_step or is_last_batch:
                if self.clip_grad_norm is not None:
                    if self._amp_enabled and self._scaler is not None:
                        self._scaler.unscale_(self.optimizer)
                    torch.nn.utils.clip_grad_norm_(
                        self.model.parameters(), self.clip_grad_norm
                    )

                if self._amp_enabled and self._scaler is not None:
                    self._scaler.step(self.optimizer)
                    self._scaler.update()
                else:
                    self.optimizer.step()

                self.optimizer.zero_grad()

                # Step non-Plateau schedulers after optimizer update
                if (
                    self.scheduler is not None
                    and not isinstance(self.scheduler, ReduceLROnPlateau)
                ):
                    self.scheduler.step()

            batch_loss = loss.item()
            total_loss += batch_loss
            num_batches += 1

            self._call_callbacks("on_batch_end", batch=batch_idx, loss=batch_loss)

        avg_loss = total_loss / max(num_batches, 1)

        # Average loss across DDP workers so the reported value is consistent
        if self._ddp:
            try:
                from mindtrace.cluster.distributed import all_reduce_mean as _arm  # noqa: PLC0415
                _t = torch.tensor(avg_loss, device=self.device)
                avg_loss = float(_arm(_t).item())
            except ImportError:
                try:
                    import torch.distributed as _dist  # noqa: PLC0415
                    if _dist.is_initialized() and _dist.get_world_size() > 1:
                        _t = torch.tensor(avg_loss, device=self.device)
                        _dist.all_reduce(_t, op=_dist.ReduceOp.SUM)
                        avg_loss = float((_t / _dist.get_world_size()).item())
                except ImportError:
                    pass

        return {"train/loss": avg_loss}

    def _val_epoch(self, loader: Any) -> dict[str, float]:
        """Execute one full validation epoch.

        Runs without gradient computation and without modifying model state.

        Args:
            loader: Iterable of validation batches.

        Returns:
            Dict with a single key ``"val/loss"`` mapped to the mean batch
            loss over the validation set.
        """
        self.model.eval()

        total_loss = 0.0
        num_batches = 0

        with torch.no_grad():
            for raw_batch in loader:
                inputs, targets = self._unpack_batch(raw_batch)
                inputs = self._to_device(inputs)
                targets = self._to_device(targets)

                if self._amp_enabled:
                    with torch.amp.autocast(device_type=self.device.type):
                        outputs = self.model(inputs)
                        loss = self.loss_fn(outputs, targets)
                else:
                    outputs = self.model(inputs)
                    loss = self.loss_fn(outputs, targets)

                total_loss += loss.item()
                num_batches += 1

        avg_loss = total_loss / max(num_batches, 1)
        return {"val/loss": avg_loss}

    # ------------------------------------------------------------------
    # Utility helpers
    # ------------------------------------------------------------------

    def _unpack_batch(self, batch: Any) -> tuple[Any, Any]:
        """Extract ``(inputs, targets)`` from a raw batch.

        Uses ``self.batch_fn`` when provided; otherwise falls back to tuple
        unpacking.

        Args:
            batch: Raw batch object from the data loader.

        Returns:
            A 2-tuple ``(inputs, targets)``.

        Raises:
            TypeError: If the batch cannot be unpacked as a 2-element tuple
                and no ``batch_fn`` was supplied.
        """
        if self.batch_fn is not None:
            return self.batch_fn(batch)

        try:
            inputs, targets = batch
        except (TypeError, ValueError) as exc:
            raise TypeError(
                "Trainer: cannot unpack batch into (inputs, targets). "
                "Provide a 'batch_fn' to handle this batch layout."
            ) from exc

        return inputs, targets

    def _to_device(self, data: Any) -> Any:
        """Move *data* to ``self.device``.

        Handles tensors directly and dicts whose values are tensors.

        Args:
            data: A ``torch.Tensor`` or a ``dict`` mapping strings to
                ``torch.Tensor`` instances.

        Returns:
            The same structure with all tensors moved to ``self.device``.
        """
        if isinstance(data, torch.Tensor):
            return data.to(self.device)

        if isinstance(data, dict):
            return {k: v.to(self.device) if isinstance(v, torch.Tensor) else v
                    for k, v in data.items()}

        if isinstance(data, (list, tuple)):
            moved = [self._to_device(v) for v in data]
            return type(data)(moved)

        # Fallback: return unchanged (e.g. custom types)
        return data

    def _call_callbacks(self, event: str, **kwargs: Any) -> None:
        """Dispatch an event to all registered callbacks.

        Args:
            event: Name of the hook method to call (e.g. ``"on_epoch_end"``).
            **kwargs: Keyword arguments forwarded to the callback hook alongside
                the ``trainer`` reference.

        Note:
            Exceptions raised inside a callback are caught and logged at ERROR
            level so that one misbehaving callback cannot abort the training run.
        """
        for cb in self.callbacks:
            method = getattr(cb, event, None)
            if method is None:
                continue
            try:
                method(self, **kwargs)
            except Exception as exc:
                logger.error(
                    "Trainer: callback %s.%s raised an exception: %s",
                    type(cb).__name__,
                    event,
                    exc,
                    exc_info=True,
                )

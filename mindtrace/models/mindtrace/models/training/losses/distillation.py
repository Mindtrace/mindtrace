"""Knowledge-distillation losses for the MindTrace training pillar.

Provides:
- ``DistillationLoss``: Hinton-style knowledge distillation combining a base
  supervised loss with a temperature-scaled KL-divergence term against a
  teacher model's logits, optionally augmented with a feature-matching term.
- ``FeatureDistillation``: FitNets-style intermediate-feature matching between
  student and teacher submodules via forward hooks.
"""

from __future__ import annotations

from typing import Callable, Sequence

import torch.nn as nn
import torch.nn.functional as F
from torch import Tensor
from torch.utils.hooks import RemovableHandle


class FeatureDistillation(nn.Module):
    """FitNets-style feature distillation between student and teacher layers.

    Registers forward hooks on paired student/teacher submodules so that
    intermediate activations are captured transparently during the normal
    forward passes a trainer already performs.  :meth:`compute` then returns
    the mean MSE between each student activation and its (detached) teacher
    counterpart, which can be added to a logit-distillation loss (see
    ``DistillationLoss(features=...)``).

    Shape handling:

    * **Channel mismatch** — when the student and teacher activations have a
      different channel/feature dimension, a lazy projection layer is created
      on the first :meth:`compute` call: a 1x1 ``Conv2d`` for 4-D activations
      or a ``Linear`` for 2-D activations, mapping student channels to teacher
      channels.  Projections are moved to the activation's device and
      registered as submodules, so ``.parameters()`` exposes them.
    * **Spatial mismatch** — 4-D teacher activations are adaptively
      average-pooled to the student's spatial size before the MSE.

    .. important::
        Projection layers are **trainable** and must be optimized alongside
        the student, so the optimizer must include
        ``feature_distiller.parameters()`` whenever projections are possible
        (i.e. whenever paired layers may differ in width).  Because
        projections are created lazily, run one warm-up forward pass through
        both models followed by :meth:`compute` *before* building the
        optimizer so the projection parameters exist:

        Example::

            fd = FeatureDistillation(student, teacher, [("backbone.layer3", "backbone.layer3")])
            student(x); teacher(x); fd.compute()   # warm-up materialises projections
            optimizer = AdamW([*student.parameters(), *fd.parameters()], lr=1e-3)
            criterion = DistillationLoss(nn.CrossEntropyLoss(), features=fd)

    Args:
        student: The student model whose submodules are hooked.
        teacher: The teacher model whose submodules are hooked.  Teacher
            activations are detached, so no gradients flow to the teacher.
        pairs: Sequence of ``(student_submodule_name, teacher_submodule_name)``
            dotted names resolved via ``nn.Module.get_submodule``.
        weight_per_pair: Optional per-pair weights for the MSE terms.  When
            ``None`` all pairs are weighted equally.  :meth:`compute` returns
            the weighted mean ``sum(w_i * mse_i) / sum(w_i)``.

    Raises:
        ValueError: If *pairs* is empty or *weight_per_pair* has a different
            length than *pairs*.
        KeyError: If a submodule name cannot be resolved; the message lists
            the available submodule names of the offending model.

    Reference:
        Romero, A. et al. "FitNets: Hints for Thin Deep Nets." ICLR 2015.
    """

    def __init__(
        self,
        student: nn.Module,
        teacher: nn.Module,
        pairs: Sequence[tuple[str, str]],
        *,
        weight_per_pair: Sequence[float] | None = None,
    ) -> None:
        super().__init__()
        pairs = list(pairs)
        if not pairs:
            raise ValueError("FeatureDistillation: pairs must contain at least one (student, teacher) name pair")
        if weight_per_pair is not None and len(weight_per_pair) != len(pairs):
            raise ValueError(
                f"FeatureDistillation: weight_per_pair has {len(weight_per_pair)} entries "
                f"but there are {len(pairs)} pairs"
            )

        self.pairs: list[tuple[str, str]] = pairs
        self.pair_weights: list[float] = (
            [float(w) for w in weight_per_pair] if weight_per_pair is not None else [1.0] * len(pairs)
        )
        # Lazy student->teacher projections, keyed by pair index (str for ModuleDict).
        self.projections = nn.ModuleDict()

        self._student_feats: dict[int, Tensor] = {}
        self._teacher_feats: dict[int, Tensor] = {}
        self._handles: list[RemovableHandle] = []

        for index, (student_name, teacher_name) in enumerate(pairs):
            student_module = self._resolve_submodule(student, student_name, role="student")
            teacher_module = self._resolve_submodule(teacher, teacher_name, role="teacher")
            self._handles.append(student_module.register_forward_hook(self._make_hook(index, is_student=True)))
            self._handles.append(teacher_module.register_forward_hook(self._make_hook(index, is_student=False)))

    @staticmethod
    def _resolve_submodule(model: nn.Module, name: str, *, role: str) -> nn.Module:
        """Resolve *name* on *model* or raise ``KeyError`` listing valid names."""
        try:
            return model.get_submodule(name)
        except AttributeError:
            available = sorted(n for n, _ in model.named_modules() if n)
            raise KeyError(
                f"FeatureDistillation: {role} model has no submodule '{name}'. Available submodules: {available}"
            ) from None

    def _make_hook(self, index: int, *, is_student: bool) -> Callable:
        """Build a forward hook that stores the activation for pair *index*."""

        def hook(_module: nn.Module, _inputs: tuple, output: Tensor) -> None:
            if not isinstance(output, Tensor):
                raise TypeError(
                    f"FeatureDistillation: hooked {'student' if is_student else 'teacher'} submodule "
                    f"for pair {self.pairs[index]} returned {type(output).__name__}, expected a Tensor"
                )
            if is_student:
                self._student_feats[index] = output
            else:
                self._teacher_feats[index] = output.detach()

        return hook

    def compute(self) -> Tensor:
        """Return the weighted mean MSE over pairs from the latest forwards.

        Returns:
            Scalar loss tensor differentiable w.r.t. the student (and any
            projection layers); teacher activations are detached.

        Raises:
            RuntimeError: If called before both the student and the teacher
                have run a forward pass through every hooked submodule.
        """
        missing = [
            self.pairs[i]
            for i in range(len(self.pairs))
            if i not in self._student_feats or i not in self._teacher_feats
        ]
        if missing:
            raise RuntimeError(
                "FeatureDistillation.compute() called before activations were captured for pairs "
                f"{missing}. Run a forward pass through both the student and the teacher first "
                "(the Trainer does this automatically each batch)."
            )

        total: Tensor | None = None
        for index in range(len(self.pairs)):
            student_feat = self._student_feats[index]
            teacher_feat = self._teacher_feats[index]

            if student_feat.dim() != teacher_feat.dim():
                raise RuntimeError(
                    f"FeatureDistillation: pair {self.pairs[index]} captured activations with "
                    f"mismatched ranks ({student_feat.dim()}-D student vs {teacher_feat.dim()}-D teacher); "
                    "pair layers whose outputs have the same dimensionality."
                )

            student_feat = self._project(index, student_feat, teacher_feat)

            # Spatial mismatch: pool teacher features down/up to the student grid.
            if student_feat.dim() == 4 and student_feat.shape[2:] != teacher_feat.shape[2:]:
                teacher_feat = F.adaptive_avg_pool2d(teacher_feat, student_feat.shape[2:])

            pair_loss = self.pair_weights[index] * F.mse_loss(student_feat, teacher_feat)
            total = pair_loss if total is None else total + pair_loss

        assert total is not None  # len(pairs) >= 1
        return total / sum(self.pair_weights)

    def _project(self, index: int, student_feat: Tensor, teacher_feat: Tensor) -> Tensor:
        """Project student channels to teacher channels, lazily building the layer."""
        key = str(index)
        if key not in self.projections:
            if student_feat.dim() not in (2, 4):
                raise RuntimeError(
                    f"FeatureDistillation: pair {self.pairs[index]} produced a {student_feat.dim()}-D "
                    "activation; only 2-D (N, C) and 4-D (N, C, H, W) activations are supported."
                )
            if student_feat.shape[1] == teacher_feat.shape[1]:
                return student_feat  # no projection needed
            projection: nn.Module
            if student_feat.dim() == 4:
                projection = nn.Conv2d(student_feat.shape[1], teacher_feat.shape[1], kernel_size=1, bias=False)
            else:
                projection = nn.Linear(student_feat.shape[1], teacher_feat.shape[1], bias=False)
            self.projections[key] = projection.to(device=student_feat.device, dtype=student_feat.dtype)
        return self.projections[key](student_feat)

    def clear(self) -> None:
        """Drop all captured activations (hooks stay registered)."""
        self._student_feats.clear()
        self._teacher_feats.clear()

    def remove(self) -> None:
        """Remove all forward hooks and drop captured activations."""
        for handle in self._handles:
            handle.remove()
        self._handles.clear()
        self.clear()

    def __enter__(self) -> "FeatureDistillation":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.remove()

    def extra_repr(self) -> str:
        return f"pairs={self.pairs}, weights={self.pair_weights}"


class DistillationLoss(nn.Module):
    """Knowledge-distillation loss (Hinton et al., 2015).

    Combines a standard supervised loss on the ground-truth targets with a
    soft-target term that pulls the student's output distribution towards the
    teacher's:

    .. math::

        \\mathcal{L} = (1 - \\alpha) \\cdot \\mathcal{L}_{base}(z_s, y)
                     + \\alpha \\cdot T^2 \\cdot
                       KL\\big(\\log\\sigma(z_s / T) \\,\\|\\, \\sigma(z_t / T)\\big)

    where :math:`z_s` are the student logits, :math:`z_t` the teacher logits,
    :math:`\\sigma` the softmax, :math:`T` the temperature, and
    :math:`\\alpha` the distillation weight.  The :math:`T^2` factor keeps the
    soft-target gradient magnitude comparable across temperatures.

    When ``teacher_outputs`` is not provided the loss degenerates to the base
    loss alone, so it can be used as a drop-in replacement for the base loss.

    When *features* is set, ``feature_weight * features.compute()`` is added
    on top of the logit term — but only in distillation mode, i.e. when
    ``teacher_outputs`` is not ``None``.  Because ``FeatureDistillation`` may
    lazily create trainable projection layers, the optimizer must include
    ``features.parameters()`` whenever the paired layers can differ in width
    (see :class:`FeatureDistillation`).

    Args:
        base: Base supervised loss called as ``base(outputs, targets)``,
            e.g. ``nn.CrossEntropyLoss()``.
        alpha: Weight of the distillation term in ``[0, 1]``.  ``0.0``
            recovers the base loss exactly; ``1.0`` trains on soft targets
            only.
        temperature: Softmax temperature ``T`` used to soften both student
            and teacher logits.  Must be > 0.
        features: Optional :class:`FeatureDistillation` providing an
            intermediate feature-matching term.
        feature_weight: Weight of the feature term.  Must be >= 0.  Ignored
            when *features* is ``None``.

    Reference:
        Hinton, G., Vinyals, O., Dean, J. "Distilling the Knowledge in a
        Neural Network." NeurIPS 2015 Deep Learning Workshop.

    Example::

        criterion = DistillationLoss(nn.CrossEntropyLoss(), alpha=0.7, temperature=4.0)
        loss = criterion(student_logits, targets, teacher_outputs=teacher_logits)
    """

    def __init__(
        self,
        base: nn.Module | Callable,
        alpha: float = 0.7,
        temperature: float = 4.0,
        *,
        features: "FeatureDistillation | None" = None,
        feature_weight: float = 0.3,
    ) -> None:
        super().__init__()
        if not callable(base):
            raise TypeError(f"DistillationLoss: base must be callable, got {type(base).__name__}")
        if not 0.0 <= alpha <= 1.0:
            raise ValueError(f"DistillationLoss: alpha must be in [0, 1], got {alpha}")
        if temperature <= 0:
            raise ValueError(f"DistillationLoss: temperature must be > 0, got {temperature}")
        if feature_weight < 0:
            raise ValueError(f"DistillationLoss: feature_weight must be >= 0, got {feature_weight}")
        self.base = base
        self.alpha = alpha
        self.temperature = temperature
        self.features = features
        self.feature_weight = feature_weight

    def forward(
        self,
        outputs: Tensor,
        targets: Tensor,
        teacher_outputs: Tensor | None = None,
    ) -> Tensor:
        """Compute the combined distillation loss.

        Args:
            outputs: Student logits of shape ``(N, C)``.
            targets: Ground-truth targets as expected by the base loss,
                typically integer class indices of shape ``(N,)``.
            teacher_outputs: Teacher logits of shape ``(N, C)``.  When
                ``None`` only the base loss is returned (the feature term,
                if configured, is skipped as well).

        Returns:
            Scalar loss tensor.
        """
        base_loss: Tensor = self.base(outputs, targets)
        if teacher_outputs is None:
            return base_loss

        t = self.temperature
        kd_loss = F.kl_div(
            F.log_softmax(outputs / t, dim=1),
            F.softmax(teacher_outputs / t, dim=1),
            reduction="batchmean",
        ) * (t * t)

        loss = (1.0 - self.alpha) * base_loss + self.alpha * kd_loss
        if self.features is not None:
            loss = loss + self.feature_weight * self.features.compute()
        return loss

    def extra_repr(self) -> str:
        return f"alpha={self.alpha}, temperature={self.temperature}, feature_weight={self.feature_weight}"

"""Knowledge-distillation loss for the MindTrace training pillar.

Provides:
- ``DistillationLoss``: Hinton-style knowledge distillation combining a base
  supervised loss with a temperature-scaled KL-divergence term against a
  teacher model's logits.
"""

from __future__ import annotations

from typing import Callable

import torch.nn as nn
import torch.nn.functional as F
from torch import Tensor


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

    Args:
        base: Base supervised loss called as ``base(outputs, targets)``,
            e.g. ``nn.CrossEntropyLoss()``.
        alpha: Weight of the distillation term in ``[0, 1]``.  ``0.0``
            recovers the base loss exactly; ``1.0`` trains on soft targets
            only.
        temperature: Softmax temperature ``T`` used to soften both student
            and teacher logits.  Must be > 0.

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
    ) -> None:
        super().__init__()
        if not callable(base):
            raise TypeError(f"DistillationLoss: base must be callable, got {type(base).__name__}")
        if not 0.0 <= alpha <= 1.0:
            raise ValueError(f"DistillationLoss: alpha must be in [0, 1], got {alpha}")
        if temperature <= 0:
            raise ValueError(f"DistillationLoss: temperature must be > 0, got {temperature}")
        self.base = base
        self.alpha = alpha
        self.temperature = temperature

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
                ``None`` only the base loss is returned.

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

        return (1.0 - self.alpha) * base_loss + self.alpha * kd_loss

    def extra_repr(self) -> str:
        return f"alpha={self.alpha}, temperature={self.temperature}"

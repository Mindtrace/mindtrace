"""Classification loss functions for the MindTrace training pillar.

Provides:
- ``FocalLoss``: Focal loss for class-imbalanced classification.
- ``LabelSmoothingCrossEntropy``: Cross-entropy with soft target regularisation.
- ``SupConLoss``: Supervised contrastive loss (Khosla et al., 2020).
"""

from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch import Tensor


class FocalLoss(nn.Module):
    """Focal loss for addressing class imbalance in classification.

    The focal loss down-weights easy, well-classified examples and focuses
    training on hard, misclassified ones:

    .. math::

        FL(p_t) = -\\alpha (1 - p_t)^{\\gamma} \\log(p_t)

    where :math:`p_t` is the model's estimated probability for the ground-truth
    class.

    Args:
        alpha: Weighting factor applied to the focal term.  A scalar weight
            applied uniformly across all classes.
        gamma: Focusing parameter.  ``gamma=0`` recovers standard cross-entropy.
            Larger values give more weight to hard samples.
        reduction: Reduction to apply to the output: ``"mean"`` (default),
            ``"sum"``, or ``"none"``.

    Example::

        criterion = FocalLoss(alpha=1.0, gamma=2.0)
        loss = criterion(logits, targets)
    """

    def __init__(
        self,
        alpha: float = 1.0,
        gamma: float = 2.0,
        reduction: str = "mean",
    ) -> None:
        super().__init__()
        if reduction not in ("mean", "sum", "none"):
            raise ValueError(
                f"reduction must be 'mean', 'sum', or 'none', got '{reduction}'"
            )
        self.alpha = alpha
        self.gamma = gamma
        self.reduction = reduction

    def forward(self, inputs: Tensor, targets: Tensor) -> Tensor:
        """Compute focal loss.

        Args:
            inputs: Raw (unnormalised) logits of shape ``(N, C)`` where *N* is
                the batch size and *C* is the number of classes.
            targets: Ground-truth class indices of shape ``(N,)``.

        Returns:
            Scalar loss tensor (when ``reduction`` is ``"mean"`` or
            ``"sum"``), or per-sample losses of shape ``(N,)`` when
            ``reduction="none"``.
        """
        # Standard cross-entropy gives us -log(p_t) per sample
        log_softmax = F.log_softmax(inputs, dim=1)
        # Gather the log-probability for the correct class: shape (N,)
        log_pt = log_softmax.gather(dim=1, index=targets.unsqueeze(1)).squeeze(1)
        pt = log_pt.exp()

        focal_term = self.alpha * (1.0 - pt) ** self.gamma
        per_sample_loss = -focal_term * log_pt

        if self.reduction == "mean":
            return per_sample_loss.mean()
        if self.reduction == "sum":
            return per_sample_loss.sum()
        return per_sample_loss

    def extra_repr(self) -> str:
        return f"alpha={self.alpha}, gamma={self.gamma}, reduction={self.reduction!r}"


class LabelSmoothingCrossEntropy(nn.Module):
    """Cross-entropy loss with label smoothing regularisation.

    Softens the one-hot targets to reduce overconfidence:

    .. math::

        \\tilde{y}_i = (1 - \\varepsilon) \\cdot \\mathbf{1}[i = y]
                     + \\varepsilon / C

    where :math:`\\varepsilon` is the smoothing factor and *C* is the number
    of classes.

    Args:
        smoothing: Label smoothing factor in ``[0, 1)``.  ``0.0`` is
            equivalent to standard cross-entropy.
        reduction: ``"mean"`` (default), ``"sum"``, or ``"none"``.

    Example::

        criterion = LabelSmoothingCrossEntropy(smoothing=0.1)
        loss = criterion(logits, targets)
    """

    def __init__(self, smoothing: float = 0.1, reduction: str = "mean") -> None:
        super().__init__()
        if not 0.0 <= smoothing < 1.0:
            raise ValueError(
                f"smoothing must be in [0, 1), got {smoothing}"
            )
        if reduction not in ("mean", "sum", "none"):
            raise ValueError(
                f"reduction must be 'mean', 'sum', or 'none', got '{reduction}'"
            )
        self.smoothing = smoothing
        self.reduction = reduction

    def forward(self, inputs: Tensor, targets: Tensor) -> Tensor:
        """Compute label-smoothed cross-entropy.

        Args:
            inputs: Logits of shape ``(N, C)``.
            targets: Integer class indices of shape ``(N,)``.

        Returns:
            Scalar or per-sample loss depending on ``self.reduction``.
        """
        num_classes = inputs.size(1)
        log_probs = F.log_softmax(inputs, dim=1)

        # Build smoothed target distribution
        with torch.no_grad():
            smooth_targets = torch.full_like(
                log_probs, fill_value=self.smoothing / num_classes
            )
            smooth_targets.scatter_(
                1,
                targets.unsqueeze(1),
                1.0 - self.smoothing + self.smoothing / num_classes,
            )

        # KL-divergence reduces to this cross-entropy form for soft targets
        per_sample_loss = -(smooth_targets * log_probs).sum(dim=1)

        if self.reduction == "mean":
            return per_sample_loss.mean()
        if self.reduction == "sum":
            return per_sample_loss.sum()
        return per_sample_loss

    def extra_repr(self) -> str:
        return f"smoothing={self.smoothing}, reduction={self.reduction!r}"


class SupConLoss(nn.Module):
    """Supervised contrastive loss (Khosla et al., NeurIPS 2020).

    Pulls together embeddings from the same class while pushing apart
    embeddings from different classes, using a temperature-scaled softmax
    over the full batch:

    .. math::

        \\mathcal{L} = \\sum_{i \\in I}
            \\frac{-1}{|P(i)|}
            \\sum_{p \\in P(i)}
            \\log \\frac{
                \\exp(z_i \\cdot z_p / \\tau)
            }{
                \\sum_{a \\in A(i)} \\exp(z_i \\cdot z_a / \\tau)
            }

    where :math:`P(i)` is the set of positives for anchor *i* (same label,
    excluding *i* itself) and :math:`A(i) = I \\setminus \\{i\\}`.

    Args:
        temperature: Temperature parameter :math:`\\tau` for the softmax.
            Typical values: 0.07–0.5.
        base_temperature: Baseline temperature for normalising the loss scale
            (Khosla et al. set both to 0.07).

    Reference:
        Khosla, P., et al. "Supervised Contrastive Learning." NeurIPS 2020.

    Example::

        criterion = SupConLoss(temperature=0.07)
        # features: (N, D) L2-normalised embeddings
        loss = criterion(features, labels)
    """

    def __init__(
        self,
        temperature: float = 0.07,
        base_temperature: float = 0.07,
    ) -> None:
        super().__init__()
        if temperature <= 0:
            raise ValueError(f"temperature must be > 0, got {temperature}")
        if base_temperature <= 0:
            raise ValueError(f"base_temperature must be > 0, got {base_temperature}")
        self.temperature = temperature
        self.base_temperature = base_temperature

    def forward(self, features: Tensor, labels: Tensor) -> Tensor:
        """Compute supervised contrastive loss.

        Args:
            features: L2-normalised embeddings of shape ``(N, D)``.  The
                caller is responsible for normalising with
                ``F.normalize(features, dim=1)`` before passing here.
            labels: Integer class indices of shape ``(N,)``.

        Returns:
            Scalar mean loss over all anchors that have at least one positive.

        Raises:
            ValueError: If *features* and *labels* have mismatched batch sizes,
                or if no anchor has a positive pair in the batch.
        """
        n = features.size(0)
        if labels.size(0) != n:
            raise ValueError(
                f"features and labels must have the same batch size, "
                f"got {n} and {labels.size(0)}"
            )
        device = features.device

        # Similarity matrix: (N, N) — dot products of L2-normalised vectors
        dot_product = torch.matmul(features, features.T)  # (N, N)
        dot_product = dot_product / self.temperature

        # Numerical stability: subtract row-wise max (like logsumexp trick)
        # We must mask out the self-contrast diagonal before computing softmax
        logits_max, _ = dot_product.max(dim=1, keepdim=True)
        logits = dot_product - logits_max.detach()

        # Mask: positive pairs share the same label (excluding self-contrast)
        labels_col = labels.unsqueeze(1)  # (N, 1)
        labels_row = labels.unsqueeze(0)  # (1, N)
        pos_mask = (labels_col == labels_row).float()  # (N, N)

        # Self-contrast mask: 1 everywhere except diagonal
        self_contrast_mask = (
            1.0 - torch.eye(n, dtype=torch.float32, device=device)
        )
        # Remove self from positive set
        pos_mask = pos_mask * self_contrast_mask

        # Logits used in the denominator: all pairs except self
        exp_logits = torch.exp(logits) * self_contrast_mask
        log_prob = logits - torch.log(exp_logits.sum(dim=1, keepdim=True) + 1e-12)

        # Mean log-probability over positives for each anchor
        num_positives = pos_mask.sum(dim=1)
        # Only keep anchors that have at least one positive
        has_positives = num_positives > 0

        if not has_positives.any():
            # No valid anchor–positive pairs in the batch — return zero loss
            return features.new_zeros(1).squeeze()

        mean_log_prob_pos = (pos_mask * log_prob).sum(dim=1)
        mean_log_prob_pos = mean_log_prob_pos[has_positives] / num_positives[has_positives]

        loss = -(self.temperature / self.base_temperature) * mean_log_prob_pos
        return loss.mean()

    def extra_repr(self) -> str:
        return (
            f"temperature={self.temperature}, "
            f"base_temperature={self.base_temperature}"
        )

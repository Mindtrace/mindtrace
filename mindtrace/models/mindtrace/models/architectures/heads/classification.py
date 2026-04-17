"""Classification head modules.

Provides three plug-and-play heads suitable for pairing with any backbone:

* :class:`LinearHead` -- single linear layer (logistic regression style).
* :class:`MLPHead` -- multi-layer perceptron with batch norm and dropout.
* :class:`MultiLabelHead` -- single linear layer for multi-label problems;
  always returns raw logits (pair with ``BCEWithLogitsLoss``).
"""

from __future__ import annotations

import torch.nn as nn
from torch import Tensor


class LinearHead(nn.Module):
    """Single linear classification head.

    Args:
        in_features: Dimensionality of the input feature vector.
        num_classes: Number of output classes.
        dropout: Dropout probability applied *before* the linear layer.
            Set to ``0.0`` (default) to disable.

    Example:
        >>> head = LinearHead(in_features=2048, num_classes=10, dropout=0.3)
        >>> x = torch.randn(4, 2048)
        >>> logits = head(x)  # shape (4, 10)
    """

    def __init__(
        self,
        in_features: int,
        num_classes: int,
        dropout: float = 0.0,
    ) -> None:
        super().__init__()

        layers: list[nn.Module] = []
        if dropout > 0.0:
            layers.append(nn.Dropout(p=dropout))
        layers.append(nn.Linear(in_features, num_classes))

        self.classifier = nn.Sequential(*layers)

    def forward(self, x: Tensor) -> Tensor:
        """Compute class logits.

        Args:
            x: Input tensor of shape ``(B, in_features)``.

        Returns:
            Raw logits of shape ``(B, num_classes)``.
        """
        return self.classifier(x)


class MLPHead(nn.Module):
    """Multi-layer perceptron classification head.

    Stacks ``num_layers - 1`` hidden blocks of the form
    ``Linear → BatchNorm1d → ReLU → Dropout``, followed by a final
    ``Linear`` projection to ``num_classes``.

    Args:
        in_features: Dimensionality of the input feature vector.
        hidden_dim: Width of all hidden layers.
        num_classes: Number of output classes.
        dropout: Dropout probability applied after each ReLU in the hidden
            layers.  Defaults to ``0.1``.
        num_layers: Total number of linear layers (including the output
            layer).  Must be ``≥ 1``.  When ``num_layers=1`` the head
            degenerates to a single linear projection (no hidden layers).

    Raises:
        ValueError: If ``num_layers < 1``.

    Example:
        >>> head = MLPHead(in_features=768, hidden_dim=512, num_classes=10)
        >>> x = torch.randn(4, 768)
        >>> logits = head(x)  # shape (4, 10)
    """

    def __init__(
        self,
        in_features: int,
        hidden_dim: int,
        num_classes: int,
        dropout: float = 0.1,
        num_layers: int = 2,
    ) -> None:
        if num_layers < 1:
            raise ValueError(f"num_layers must be >= 1, got {num_layers}.")
        super().__init__()

        layers: list[nn.Module] = []
        current_dim = in_features

        for _ in range(num_layers - 1):
            layers.extend(
                [
                    nn.Linear(current_dim, hidden_dim),
                    nn.BatchNorm1d(hidden_dim),
                    nn.ReLU(inplace=True),
                    nn.Dropout(p=dropout),
                ]
            )
            current_dim = hidden_dim

        # Output projection.
        layers.append(nn.Linear(current_dim, num_classes))

        self.mlp = nn.Sequential(*layers)

    def forward(self, x: Tensor) -> Tensor:
        """Compute class logits.

        Args:
            x: Input tensor of shape ``(B, in_features)``.

        Returns:
            Raw logits of shape ``(B, num_classes)``.
        """
        return self.mlp(x)


class MultiLabelHead(nn.Module):
    """Linear head for multi-label classification.

    Returns **raw logits** unconditionally.  During training, pair with
    ``torch.nn.BCEWithLogitsLoss``; during inference, apply ``torch.sigmoid``
    to the output.

    Args:
        in_features: Dimensionality of the input feature vector.
        num_classes: Number of independent binary labels.
        dropout: Dropout probability applied *before* the linear layer.
            Set to ``0.0`` (default) to disable.

    Example:
        >>> head = MultiLabelHead(in_features=2048, num_classes=80)
        >>> x = torch.randn(4, 2048)
        >>> logits = head(x)  # shape (4, 80) — raw logits
        >>> probs = torch.sigmoid(logits)  # apply during inference
    """

    def __init__(
        self,
        in_features: int,
        num_classes: int,
        dropout: float = 0.0,
    ) -> None:
        super().__init__()

        layers: list[nn.Module] = []
        if dropout > 0.0:
            layers.append(nn.Dropout(p=dropout))
        layers.append(nn.Linear(in_features, num_classes))

        self.classifier = nn.Sequential(*layers)

    def forward(self, x: Tensor) -> Tensor:
        """Compute per-label logits.

        Returns raw logits regardless of ``self.training``.  The caller is
        responsible for applying ``torch.sigmoid`` at inference time or using
        ``BCEWithLogitsLoss`` during training.

        Args:
            x: Input tensor of shape ``(B, in_features)``.

        Returns:
            Raw logits of shape ``(B, num_classes)``.
        """
        return self.classifier(x)

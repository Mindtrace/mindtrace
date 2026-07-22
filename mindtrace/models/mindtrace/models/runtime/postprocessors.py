"""Postprocessors for runnable Mindtrace models."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from torch import Tensor

from mindtrace.models.serving.results import ClassificationResult


class ClassificationPostprocessor:
    """Convert classification logits into labelled confidence results."""

    def __init__(self, labels: Sequence[str] | None = None) -> None:
        self.labels = list(labels) if labels is not None else None

    def __call__(
        self,
        logits: Tensor,
        *,
        include_probabilities: bool = False,
        **_: Any,
    ) -> list[ClassificationResult]:
        if logits.ndim != 2:
            raise ValueError(
                "classification logits must have shape (B, C), "
                f"got {tuple(logits.shape)}"
            )

        probabilities = logits.softmax(dim=-1).detach().cpu()
        class_ids = probabilities.argmax(dim=-1)
        results: list[ClassificationResult] = []

        for index, class_id_tensor in enumerate(class_ids):
            class_id = int(class_id_tensor.item())
            if self.labels is not None and class_id >= len(self.labels):
                raise ValueError(f"class index {class_id} has no corresponding label")

            extra: dict[str, Any] = {"class_id": class_id}
            if include_probabilities:
                extra["probabilities"] = probabilities[index].tolist()

            results.append(
                ClassificationResult(
                    cls=self.labels[class_id] if self.labels is not None else str(class_id),
                    confidence=float(probabilities[index, class_id].item()),
                    extra=extra,
                )
            )

        return results


__all__ = ["ClassificationPostprocessor"]

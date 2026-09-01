"""Output postprocessors for task-level models."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from torch import Tensor

from mindtrace.models.serving.results import ClassificationResult


class ClassificationPostprocessor:
    """Convert classification logits into labelled confidence results."""

    def __init__(self, labels: Sequence[str] | None = None) -> None:
        if labels is None:
            self.labels = None
            return
        if isinstance(labels, (str, bytes)):
            raise TypeError("labels must be a sequence of strings, not a single string or bytes value")

        normalized_labels = list(labels)
        if not all(isinstance(label, str) for label in normalized_labels):
            raise TypeError("labels must contain only strings")
        self.labels = normalized_labels

    def __call__(
        self,
        logits: Tensor,
        *,
        include_probabilities: bool = False,
    ) -> list[ClassificationResult]:
        if logits.ndim != 2:
            raise ValueError(f"classification logits must have shape (B, C), got {tuple(logits.shape)}")
        if self.labels is not None and logits.shape[-1] != len(self.labels):
            raise ValueError(
                f"classification logits contain {logits.shape[-1]} classes, but {len(self.labels)} labels were provided"
            )

        probabilities = logits.softmax(dim=-1).detach().cpu()
        class_ids = probabilities.argmax(dim=-1)
        results: list[ClassificationResult] = []

        for index, class_id_tensor in enumerate(class_ids):
            class_id = int(class_id_tensor.item())

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

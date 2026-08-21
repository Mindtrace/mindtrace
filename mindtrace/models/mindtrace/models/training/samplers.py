"""Sampling policies for model training."""

from __future__ import annotations

import random
from collections.abc import Hashable, Iterator, Sequence

from torch.utils.data import Sampler


def _require_positive_int(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")


def _require_hashable(name: str, values: Sequence[Hashable]) -> None:
    for index, value in enumerate(values):
        try:
            hash(value)
        except TypeError as exc:
            raise TypeError(f"{name}[{index}] must be hashable") from exc


class GroupedClassBatchSampler(Sampler[list[int]]):
    """Build class-balanced batches whose same-class samples use distinct groups.

    Classes, groups, and observations are sampled uniformly. Selection is without
    replacement within a batch and with replacement between batches. A class is
    eligible only when it contains at least ``samples_per_class`` distinct groups.

    Args:
        labels: Class label for each dataset sample.
        group_ids: Group identifier for each dataset sample. Composite identities
            may be represented by tuples.
        classes_per_batch: Number of distinct classes in each batch.
        samples_per_class: Number of distinct groups sampled for each class.
        batches_per_epoch: Number of batches yielded per epoch. When omitted, uses
            ``len(labels) // (classes_per_batch * samples_per_class)``.
        seed: Base seed for deterministic sampling. The effective seed is
            ``seed + epoch``.

    Raises:
        TypeError: If configuration values have invalid types or labels/group IDs
            are not hashable.
        ValueError: If the inputs or sampling configuration cannot form batches.
    """

    def __init__(
        self,
        labels: Sequence[Hashable],
        group_ids: Sequence[Hashable],
        *,
        classes_per_batch: int,
        samples_per_class: int,
        batches_per_epoch: int | None = None,
        seed: int = 0,
    ) -> None:
        _require_positive_int("classes_per_batch", classes_per_batch)
        _require_positive_int("samples_per_class", samples_per_class)
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise TypeError("seed must be an integer")

        materialized_labels = tuple(labels)
        materialized_group_ids = tuple(group_ids)
        if len(materialized_labels) != len(materialized_group_ids):
            raise ValueError("labels and group_ids must contain the same number of items")
        if not materialized_labels:
            raise ValueError("labels and group_ids must not be empty")
        _require_hashable("labels", materialized_labels)
        _require_hashable("group_ids", materialized_group_ids)

        index: dict[Hashable, dict[Hashable, list[int]]] = {}
        for sample_index, (label, group_id) in enumerate(zip(materialized_labels, materialized_group_ids, strict=True)):
            index.setdefault(label, {}).setdefault(group_id, []).append(sample_index)

        eligible_labels = tuple(label for label, groups in index.items() if len(groups) >= samples_per_class)
        if len(eligible_labels) < classes_per_batch:
            raise ValueError(
                "Grouped sampling requires "
                f"{classes_per_batch} eligible classes with at least "
                f"{samples_per_class} distinct groups each; found {len(eligible_labels)}."
            )

        batch_size = classes_per_batch * samples_per_class
        if batches_per_epoch is None:
            batches_per_epoch = len(materialized_labels) // batch_size
            if batches_per_epoch == 0:
                raise ValueError(
                    "The default batches_per_epoch is zero; provide enough samples or set batches_per_epoch explicitly."
                )
        else:
            _require_positive_int("batches_per_epoch", batches_per_epoch)

        self.classes_per_batch = classes_per_batch
        self.samples_per_class = samples_per_class
        self.batches_per_epoch = batches_per_epoch
        self.seed = seed
        self.epoch = 0
        self.batch_size = batch_size
        self.eligible_labels = eligible_labels
        self._index = index
        self._groups_by_label = {label: tuple(index[label]) for label in eligible_labels}

    def __iter__(self) -> Iterator[list[int]]:
        rng = random.Random(self.seed + self.epoch)
        for _ in range(self.batches_per_epoch):
            selected_labels = rng.sample(self.eligible_labels, self.classes_per_batch)
            batch: list[int] = []
            for label in selected_labels:
                selected_groups = rng.sample(
                    self._groups_by_label[label],
                    self.samples_per_class,
                )
                for group_id in selected_groups:
                    batch.append(rng.choice(self._index[label][group_id]))
            rng.shuffle(batch)
            yield batch

    def __len__(self) -> int:
        return self.batches_per_epoch

    def set_epoch(self, epoch: int) -> None:
        """Set the epoch used to derive deterministic sampling order."""

        if isinstance(epoch, bool) or not isinstance(epoch, int):
            raise TypeError("epoch must be an integer")
        if epoch < 0:
            raise ValueError("epoch must be greater than or equal to zero")
        self.epoch = epoch


__all__ = ["GroupedClassBatchSampler"]

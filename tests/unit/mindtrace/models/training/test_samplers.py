"""Unit tests for training samplers."""

from __future__ import annotations

from collections import Counter, defaultdict

import pytest

from mindtrace.models.training import GroupedClassBatchSampler


def _sampling_data() -> tuple[list[int], list[tuple[str, int]]]:
    labels: list[int] = []
    group_ids: list[tuple[str, int]] = []
    for label in range(3):
        for group in range(4):
            observations = 2 if group == 0 else 1
            for _ in range(observations):
                labels.append(label)
                group_ids.append((f"subject-{label}", group))
    return labels, group_ids


def test_batches_contain_configured_classes_and_distinct_groups():
    labels, group_ids = _sampling_data()
    sampler = GroupedClassBatchSampler(
        labels,
        group_ids,
        classes_per_batch=2,
        samples_per_class=3,
        batches_per_epoch=5,
        seed=17,
    )

    assert len(sampler) == 5
    assert sampler.batch_size == 6
    for batch in sampler:
        batch_labels = [labels[index] for index in batch]
        assert set(Counter(batch_labels).values()) == {3}
        assert len(set(batch_labels)) == 2

        groups_by_label: dict[int, set[tuple[str, int]]] = defaultdict(set)
        for index in batch:
            groups_by_label[labels[index]].add(group_ids[index])
        assert all(len(groups) == 3 for groups in groups_by_label.values())


def test_same_seed_and_epoch_produce_the_same_batches():
    labels, group_ids = _sampling_data()
    kwargs = {
        "classes_per_batch": 2,
        "samples_per_class": 2,
        "batches_per_epoch": 8,
        "seed": 23,
    }
    first = GroupedClassBatchSampler(labels, group_ids, **kwargs)
    second = GroupedClassBatchSampler(labels, group_ids, **kwargs)

    assert list(first) == list(second)

    first.set_epoch(4)
    second.set_epoch(4)
    epoch_four_batches = list(first)
    assert epoch_four_batches == list(second)

    first.set_epoch(5)
    assert list(first) != epoch_four_batches


def test_default_epoch_length_matches_drop_last_pass():
    labels, group_ids = _sampling_data()
    sampler = GroupedClassBatchSampler(
        labels,
        group_ids,
        classes_per_batch=2,
        samples_per_class=2,
    )

    assert len(sampler) == len(labels) // 4


def test_rare_classes_are_excluded_when_enough_classes_remain():
    labels = [0, 0, 1, 1, 2, 2]
    group_ids = ["a", "b", "c", "d", "rare", "rare"]
    sampler = GroupedClassBatchSampler(
        labels,
        group_ids,
        classes_per_batch=2,
        samples_per_class=2,
        batches_per_epoch=4,
    )

    assert sampler.eligible_labels == (0, 1)
    assert {labels[index] for batch in sampler for index in batch} == {0, 1}


@pytest.mark.parametrize(
    ("labels", "group_ids", "message"),
    [
        ([], [], "must not be empty"),
        ([0], [], "same number"),
        ([[0]], ["group"], "labels\\[0\\] must be hashable"),
        ([0], [["group"]], "group_ids\\[0\\] must be hashable"),
    ],
)
def test_rejects_invalid_input_sequences(labels, group_ids, message):
    with pytest.raises((TypeError, ValueError), match=message):
        GroupedClassBatchSampler(
            labels,
            group_ids,
            classes_per_batch=1,
            samples_per_class=1,
        )


@pytest.mark.parametrize(
    ("name", "value", "error_type", "message"),
    [
        ("classes_per_batch", 0, ValueError, "greater than zero"),
        ("classes_per_batch", True, TypeError, "must be an integer"),
        ("samples_per_class", -1, ValueError, "greater than zero"),
        ("samples_per_class", 1.5, TypeError, "must be an integer"),
        ("batches_per_epoch", 0, ValueError, "greater than zero"),
        ("batches_per_epoch", False, TypeError, "must be an integer"),
        ("seed", False, TypeError, "must be an integer"),
    ],
)
def test_rejects_invalid_configuration(name, value, error_type, message):
    kwargs = {
        "classes_per_batch": 1,
        "samples_per_class": 1,
        "batches_per_epoch": 1,
        "seed": 0,
    }
    kwargs[name] = value

    with pytest.raises(error_type, match=message):
        GroupedClassBatchSampler([0], ["group"], **kwargs)


def test_rejects_too_few_eligible_classes():
    with pytest.raises(ValueError, match=r"2 eligible classes.*found 1"):
        GroupedClassBatchSampler(
            [0, 0, 1, 1],
            ["a", "b", "rare", "rare"],
            classes_per_batch=2,
            samples_per_class=2,
        )


@pytest.mark.parametrize(
    ("epoch", "error_type", "message"),
    [
        (-1, ValueError, "greater than or equal to zero"),
        (True, TypeError, "must be an integer"),
        (1.5, TypeError, "must be an integer"),
    ],
)
def test_set_epoch_rejects_invalid_values(epoch, error_type, message):
    sampler = GroupedClassBatchSampler(
        [0],
        ["group"],
        classes_per_batch=1,
        samples_per_class=1,
    )

    with pytest.raises(error_type, match=message):
        sampler.set_epoch(epoch)

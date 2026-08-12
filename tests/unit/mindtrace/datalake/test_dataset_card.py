from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from mindtrace.datalake import (
    AnnotationField,
    DatasetCard,
    DatasetProvenance,
    DatasetSource,
    DatasetStatistic,
    SplitInfo,
)
from mindtrace.datalake.service_types import CreateDatasetVersionInput


def test_dataset_card_to_dict_roundtrip():
    card = DatasetCard(
        summary="Image classification dataset.",
        task="classification",
        modalities=["image"],
        sources=[DatasetSource(name="source-dataset", version="1.0.0", dataset_version_id="dataset_version_1")],
        provenance=DatasetProvenance(
            creation_method="Reviewed importer",
            included_subsets=["production"],
            excluded_subsets=["repeated-observations"],
            split_strategy="Deterministic stratification by class",
            split_seed=42,
            split_key="source_path",
            reproduction_notes=["Rare classes are allocated before the majority class"],
        ),
        splits={
            "train": SplitInfo(
                count=10,
                percentage=83.33,
                source_subsets=["production"],
                selection_criteria="Training allocation",
                statistics=[DatasetStatistic(name="defective", value=4, unit="items")],
            ),
            "val": SplitInfo(count=2, description="held-out validation"),
        },
        annotations=[AnnotationField(name="defect_type", kind="classification", labels=["healthy", "defective"])],
        summary_statistics=[DatasetStatistic(name="total_items", value=12, unit="items")],
        evaluation_notes=["Validate rare classes separately"],
        intended_uses=["Train defect classifiers"],
        out_of_scope_uses=["General consumer photography"],
        limitations=["Small validation split"],
        markdown="## Notes\n\n| split | count |\n| --- | ---: |\n| train | 10 |",
        extra={"importer": "unit"},
    )

    restored = DatasetCard.from_dict(card.to_dict())

    assert restored == card
    assert restored.schema_version == 1
    assert restored.provenance.split_key == "source_path"
    assert restored.splits["train"].count == 10
    assert restored.splits["train"].statistics[0].value == 4
    assert restored.annotations[0].labels == ["healthy", "defective"]


def test_dataset_card_save_and_load_json(tmp_path):
    card = DatasetCard(summary="Demo dataset", splits={"test": {"count": 3}})
    path = tmp_path / "nested" / "card.json"

    card.save_json(path)

    assert json.loads(path.read_text(encoding="utf-8"))["summary"] == "Demo dataset"
    assert DatasetCard.load_json(path) == card


def test_create_dataset_version_input_accepts_card_dict():
    payload = CreateDatasetVersionInput(
        dataset_name="demo",
        version="0.1.0",
        manifest=[],
        card={"summary": "Demo dataset"},
    )

    assert isinstance(payload.card, DatasetCard)
    assert payload.card.summary == "Demo dataset"


@pytest.mark.parametrize(
    "payload",
    [
        {"intended_use": ["Train classifiers"]},
        {"sources": [{"name": "source", "unknown": "value"}]},
    ],
)
def test_dataset_card_rejects_unknown_fields(payload):
    with pytest.raises(ValidationError):
        DatasetCard.model_validate(payload)


def test_split_info_rejects_negative_count():
    with pytest.raises(ValidationError):
        SplitInfo(count=-1)


def test_dataset_card_rejects_non_json_extra_value():
    with pytest.raises(ValidationError):
        DatasetCard(extra={"unsupported": object()})


def test_dataset_card_rejects_unknown_schema_version():
    with pytest.raises(ValidationError):
        DatasetCard(schema_version=2)

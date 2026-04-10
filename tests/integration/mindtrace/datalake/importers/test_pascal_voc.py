from pathlib import Path

from mindtrace.datalake import Datalake
from mindtrace.datalake.importers.pascal_voc import PascalVocImportConfig, import_pascal_voc
from tests.utils.pascal_voc_coverage_cases import *  # noqa: F401,F403
from tests.utils.pascal_voc_support import build_tiny_voc_fixture


def test_pascal_voc_importer_end_to_end_with_tiny_fixture(sync_datalake: Datalake, tmp_path: Path):
    build_tiny_voc_fixture(tmp_path)

    summary = import_pascal_voc(
        sync_datalake,
        PascalVocImportConfig(
            root_dir=tmp_path,
            split="train",
            dataset_name="tiny-pascal-voc-train",
            dataset_version="1.0.0",
            download=False,
            show_progress=False,
        ),
    )

    assert summary.datum_count == 1
    assert summary.image_asset_count == 1
    assert summary.classification_record_count == 1
    assert summary.detection_record_count == 1
    assert summary.segmentation_record_count == 1

    dataset_version = sync_datalake.get_dataset_version("tiny-pascal-voc-train", "1.0.0")
    resolved = sync_datalake.resolve_datum(dataset_version.manifest[0])

    assert list(resolved.assets.keys()) == ["image"]
    annotation_set_names = {annotation_set.name for annotation_set in resolved.annotation_sets}
    assert annotation_set_names == {
        "pascal-voc-classification",
        "pascal-voc-detection",
        "pascal-voc-segmentation",
    }

    all_records = [record for records in resolved.annotation_records.values() for record in records]
    labels = {record.label for record in all_records}
    kinds = {record.kind for record in all_records}
    assert "person" in labels
    assert kinds == {"classification", "bbox", "mask"}
    segmentation_records = [record for record in all_records if record.kind == "mask"]
    assert [record.label for record in segmentation_records] == ["person"]

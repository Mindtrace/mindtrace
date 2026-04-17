from __future__ import annotations

import runpy
import sys
import tarfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from mindtrace.datalake.importers import pascal_voc
from mindtrace.datalake.types import AnnotationLabelDefinition, AnnotationSchema
from tests.utils.pascal_voc_support import VOC_XML, build_tiny_voc_fixture, make_import_datalake_mock, make_schema_ref


def test_asset_object_name_is_flattened_for_local_registry_backend():
    name = pascal_voc._asset_object_name("imports/pascal-voc-2012/demo/1.0.0", "train", "images", "2008_000008.jpg")

    assert "/" not in name
    assert name.endswith("__train__images__2008_000008.jpg")


def test_default_dataset_name_and_voc_root_resolution(tmp_path: Path):
    assert pascal_voc._default_dataset_name("val") == "pascal-voc-2012-val"

    direct_base = tmp_path / "direct"
    direct_root = direct_base / "VOC2012"
    direct_root.mkdir(parents=True)
    assert pascal_voc._voc_root_from_base(direct_base) == direct_root

    nested_base = tmp_path / "nested"
    nested_root = nested_base / "VOCdevkit" / "VOC2012"
    nested_root.mkdir(parents=True)
    assert pascal_voc._voc_root_from_base(nested_base) == nested_root

    missing_base = tmp_path / "missing"
    assert pascal_voc._voc_root_from_base(missing_base) == missing_base / "VOCdevkit" / "VOC2012"


def test_download_archive_uses_expected_download_strategy(tmp_path: Path):
    archive_path = tmp_path / pascal_voc.PASCAL_VOC_2012_ARCHIVE_NAME

    with patch.object(pascal_voc, "download_with_progress") as download_with_progress:
        pascal_voc._download_archive("https://example.com/voc.tar", archive_path, show_progress=True)
        download_with_progress.assert_called_once_with(
            "https://example.com/voc.tar",
            archive_path,
            desc=f"Downloading {archive_path.name}",
        )

    with patch("urllib.request.urlretrieve") as urlretrieve:
        pascal_voc._download_archive("https://example.com/voc.tar", archive_path, show_progress=False)
        urlretrieve.assert_called_once_with("https://example.com/voc.tar", archive_path)


def test_safe_extract_tar_handles_filter_fallback(tmp_path: Path):
    archive_path = tmp_path / "archive.tar"
    archive_path.write_text("tar")

    def tar_context(tar_object: MagicMock) -> MagicMock:
        manager = MagicMock()
        manager.__enter__.return_value = tar_object
        manager.__exit__.return_value = False
        return manager

    first_tar = MagicMock()
    first_tar.extractall.side_effect = TypeError("filter unsupported")
    second_tar = MagicMock()

    with patch("tarfile.open", side_effect=[tar_context(first_tar), tar_context(second_tar)]) as open_tar:
        pascal_voc._safe_extract_tar(archive_path, tmp_path)

    assert open_tar.call_count == 2
    first_tar.extractall.assert_called_once_with(path=tmp_path, filter="data")
    second_tar.extractall.assert_called_once_with(path=tmp_path)


def test_download_if_missing_returns_existing_direct_root(tmp_path: Path):
    voc_root, _ = build_tiny_voc_fixture(tmp_path, direct_root=True)

    resolved = pascal_voc._download_if_missing(tmp_path, download=False, source_url="unused", show_progress=False)

    assert resolved == voc_root


def test_download_if_missing_raises_when_dataset_is_missing_and_download_disabled(tmp_path: Path):
    with pytest.raises(FileNotFoundError, match="Pass download=True"):
        pascal_voc._download_if_missing(tmp_path, download=False, source_url="unused", show_progress=False)


def test_download_if_missing_retries_after_extract_failure(tmp_path: Path):
    attempts = {"download": 0, "extract": 0}
    nested_root = tmp_path / "VOCdevkit" / "VOC2012"

    def fake_download(source_url: str, archive_path: Path, *, show_progress: bool) -> None:
        assert source_url == "https://example.com/voc.tar"
        assert show_progress is False
        attempts["download"] += 1
        archive_path.write_text("archive")

    def fake_extract(archive_path: Path, root_dir: Path) -> None:
        attempts["extract"] += 1
        if attempts["extract"] == 1:
            raise tarfile.TarError("corrupt archive")
        nested_root.mkdir(parents=True)

    with (
        patch.object(pascal_voc, "_download_archive", side_effect=fake_download),
        patch.object(pascal_voc, "_safe_extract_tar", side_effect=fake_extract),
    ):
        resolved = pascal_voc._download_if_missing(
            tmp_path,
            download=True,
            source_url="https://example.com/voc.tar",
            show_progress=False,
        )

    assert resolved == nested_root
    assert attempts == {"download": 2, "extract": 2}


def test_download_if_missing_raises_when_extraction_does_not_produce_voc_root(tmp_path: Path):
    def fake_download(source_url: str, archive_path: Path, *, show_progress: bool) -> None:
        archive_path.write_text("archive")

    with (
        patch.object(pascal_voc, "_download_archive", side_effect=fake_download),
        patch.object(pascal_voc, "_safe_extract_tar"),
    ):
        with pytest.raises(RuntimeError, match="could not find extracted directory"):
            pascal_voc._download_if_missing(
                tmp_path,
                download=True,
                source_url="https://example.com/voc.tar",
                show_progress=False,
            )


def test_download_if_missing_raises_runtime_error_after_final_failure(tmp_path: Path):
    def fake_download(source_url: str, archive_path: Path, *, show_progress: bool) -> None:
        archive_path.write_text("archive")

    with (
        patch.object(pascal_voc, "_download_archive", side_effect=fake_download),
        patch.object(pascal_voc, "_safe_extract_tar", side_effect=tarfile.TarError("still broken")),
    ):
        with pytest.raises(RuntimeError, match="after 2 attempts"):
            pascal_voc._download_if_missing(
                tmp_path,
                download=True,
                source_url="https://example.com/voc.tar",
                show_progress=False,
            )


def test_ensure_required_layout_raises_for_missing_directories(tmp_path: Path):
    voc_root = tmp_path / "VOCdevkit" / "VOC2012"
    (voc_root / "JPEGImages").mkdir(parents=True)

    with pytest.raises(FileNotFoundError, match="layout is incomplete"):
        pascal_voc._ensure_required_layout(voc_root)


def test_read_split_ids_handles_missing_empty_and_populated_files(tmp_path: Path):
    voc_root = tmp_path / "VOCdevkit" / "VOC2012"
    main_dir = voc_root / "ImageSets" / "Main"
    main_dir.mkdir(parents=True)

    with pytest.raises(FileNotFoundError, match="split file not found"):
        pascal_voc._read_split_ids(voc_root, "train")

    split_path = main_dir / "train.txt"
    split_path.write_text("")
    with pytest.raises(ValueError, match="is empty"):
        pascal_voc._read_split_ids(voc_root, "train")

    split_path.write_text("2008_000008\n\n")
    assert pascal_voc._read_split_ids(voc_root, "train") == ["2008_000008"]


def test_read_classification_labels_skips_invalid_and_negative_flags(tmp_path: Path):
    voc_root = tmp_path / "VOCdevkit" / "VOC2012"
    main_dir = voc_root / "ImageSets" / "Main"
    main_dir.mkdir(parents=True)

    (main_dir / "person_train.txt").write_text("img1 1\ninvalid-line\nimg2 -1\n")
    (main_dir / "dog_train.txt").write_text("img1 1\n")

    labels = pascal_voc._read_classification_labels(voc_root, "train")

    assert labels == {"img1": ["dog", "person"]}


def test_parse_detection_annotations_converts_voc_bbox_xml(tmp_path: Path):
    annotation_path = tmp_path / "sample.xml"
    annotation_path.write_text(VOC_XML)

    records = pascal_voc._parse_detection_annotations(annotation_path)

    assert len(records) == 1
    record = records[0]
    assert record["label"] == "person"
    assert record["label_id"] == pascal_voc.VOC_CLASS_TO_ID["person"]
    assert record["geometry"] == {"type": "bbox", "x": 1, "y": 2, "width": 4, "height": 6}
    assert record["attributes"]["pose"] == "Left"


def test_parse_detection_annotations_skips_unknown_classes_and_missing_boxes(tmp_path: Path):
    annotation_path = tmp_path / "sample.xml"
    annotation_path.write_text(
        """
<annotation>
  <object>
    <name>unknown</name>
    <bndbox>
      <xmin>1</xmin>
      <ymin>2</ymin>
      <xmax>3</xmax>
      <ymax>4</ymax>
    </bndbox>
  </object>
  <object>
    <name>person</name>
  </object>
</annotation>
""".strip()
    )

    assert pascal_voc._parse_detection_annotations(annotation_path) == []


def test_extract_present_segmentation_classes_builds_binary_masks(tmp_path: Path):
    mask_path = tmp_path / "mask.png"
    mask = Image.new("P", (2, 2))
    mask.putpalette([0] * (256 * 3))
    mask.putdata([0, pascal_voc.VOC_CLASS_TO_ID["person"], pascal_voc.VOC_CLASS_TO_ID["dog"], 255])
    mask.save(mask_path)

    extracted = pascal_voc._extract_present_segmentation_classes(mask_path)

    labels = [label for label, _ in extracted]
    assert labels == ["dog", "person"]

    person_mask = dict(extracted)["person"]
    assert list(person_mask.get_flattened_data()) == [0, 255, 0, 0]


def test_schema_labels_and_annotation_set_creation_helpers():
    without_background = pascal_voc._schema_labels()
    with_background = pascal_voc._schema_labels(include_background=True)

    assert without_background[0].name == "aeroplane"
    assert with_background[0].name == "background"
    assert with_background[0].id == 0

    datalake = MagicMock()
    datalake.create_annotation_set.return_value = "annotation_set"

    created = pascal_voc._create_annotation_set_if_needed(
        datalake,
        datum_id="datum_1",
        name="pascal-voc-classification",
        annotation_schema_id="schema_1",
    )

    assert created == "annotation_set"
    datalake.create_annotation_set.assert_called_once()


def test_ensure_schema_updates_existing_schema_to_include_new_optional_attrs():
    datalake = MagicMock()
    existing = AnnotationSchema(
        name="pascal-voc-classification",
        version=pascal_voc.PASCAL_VOC_SCHEMA_VERSION,
        task_type="classification",
        allowed_annotation_kinds=["classification"],
        labels=[AnnotationLabelDefinition(name="person", id=pascal_voc.VOC_CLASS_TO_ID["person"])],
        optional_attributes=[],
    )
    updated = AnnotationSchema(
        name="pascal-voc-classification",
        version=pascal_voc.PASCAL_VOC_SCHEMA_VERSION,
        task_type="classification",
        allowed_annotation_kinds=["classification"],
        labels=[AnnotationLabelDefinition(name="person", id=pascal_voc.VOC_CLASS_TO_ID["person"])],
        optional_attributes=["layer"],
    )
    datalake.get_annotation_schema_by_name_version.return_value = existing
    datalake.update_annotation_schema.return_value = updated

    result = pascal_voc._ensure_schema(
        datalake,
        name="pascal-voc-classification",
        task_type="classification",
        allowed_annotation_kinds=["classification"],
        labels=[AnnotationLabelDefinition(name="person", id=pascal_voc.VOC_CLASS_TO_ID["person"])],
        optional_attributes=["layer"],
    )

    datalake.update_annotation_schema.assert_called_once()
    assert result.optional_attributes == ["layer"]


def test_ensure_schema_creates_new_schema_when_missing():
    datalake = MagicMock()
    datalake.get_annotation_schema_by_name_version.side_effect = RuntimeError("missing")
    created = AnnotationSchema(
        name="pascal-voc-detection",
        version=pascal_voc.PASCAL_VOC_SCHEMA_VERSION,
        task_type="detection",
        allowed_annotation_kinds=["bbox"],
        labels=[AnnotationLabelDefinition(name="person", id=pascal_voc.VOC_CLASS_TO_ID["person"])],
        optional_attributes=["occluded"],
    )
    datalake.create_annotation_schema.return_value = created

    result = pascal_voc._ensure_schema(
        datalake,
        name="pascal-voc-detection",
        task_type="detection",
        allowed_annotation_kinds=["bbox"],
        labels=[AnnotationLabelDefinition(name="person", id=pascal_voc.VOC_CLASS_TO_ID["person"])],
        optional_attributes=["occluded"],
    )

    assert result == created
    datalake.create_annotation_schema.assert_called_once()


def test_ensure_schema_returns_existing_schema_after_duplicate_create():
    datalake = MagicMock()
    existing = AnnotationSchema(
        name="pascal-voc-segmentation",
        version=pascal_voc.PASCAL_VOC_SCHEMA_VERSION,
        task_type="segmentation",
        allowed_annotation_kinds=["mask"],
        labels=[AnnotationLabelDefinition(name="person", id=pascal_voc.VOC_CLASS_TO_ID["person"])],
        optional_attributes=["source_mask"],
    )
    datalake.get_annotation_schema_by_name_version.side_effect = [RuntimeError("missing"), existing]
    datalake.create_annotation_schema.side_effect = pascal_voc.DuplicateAnnotationSchemaError("duplicate")

    result = pascal_voc._ensure_schema(
        datalake,
        name="pascal-voc-segmentation",
        task_type="segmentation",
        allowed_annotation_kinds=["mask"],
        labels=[AnnotationLabelDefinition(name="person", id=pascal_voc.VOC_CLASS_TO_ID["person"])],
        optional_attributes=["source_mask"],
    )

    assert result == existing


def test_ensure_voc_schemas_builds_three_named_schema_variants():
    schemas = [make_schema_ref("classification"), make_schema_ref("detection"), make_schema_ref("segmentation")]

    with patch.object(pascal_voc, "_ensure_schema", side_effect=schemas) as ensure_schema:
        resolved = pascal_voc._ensure_voc_schemas(MagicMock())

    assert resolved == {
        "classification": schemas[0],
        "detection": schemas[1],
        "segmentation": schemas[2],
    }
    assert ensure_schema.call_count == 3


def test_iter_segmentation_masks_returns_empty_when_mask_is_missing(tmp_path: Path):
    mask_dir = tmp_path / "SegmentationClass"
    mask_dir.mkdir()

    assert list(pascal_voc._iter_segmentation_masks(mask_dir, "missing")) == []


def test_import_pascal_voc_validates_split_name(tmp_path: Path):
    datalake = MagicMock()

    with pytest.raises(ValueError, match="supports split"):
        pascal_voc.import_pascal_voc(
            datalake,
            pascal_voc.PascalVocImportConfig(root_dir=tmp_path, split="test"),
        )


def test_import_pascal_voc_rejects_existing_dataset_version(tmp_path: Path):
    build_tiny_voc_fixture(tmp_path)
    datalake = MagicMock()
    datalake.get_dataset_version.return_value = SimpleNamespace(dataset_version_id="existing")

    with pytest.raises(ValueError, match="Dataset version already exists"):
        pascal_voc.import_pascal_voc(
            datalake,
            pascal_voc.PascalVocImportConfig(
                root_dir=tmp_path,
                split="train",
                dataset_name="tiny-pascal-voc-train",
                dataset_version="1.0.0",
                show_progress=False,
            ),
        )


@pytest.mark.parametrize("missing_name", ["image", "annotation"])
def test_import_pascal_voc_raises_for_missing_payloads(tmp_path: Path, missing_name: str):
    voc_root, image_id = build_tiny_voc_fixture(tmp_path, include_segmentation=False, include_classification=False)
    if missing_name == "image":
        (voc_root / "JPEGImages" / f"{image_id}.jpg").unlink()
        expected = "image not found"
    else:
        (voc_root / "Annotations" / f"{image_id}.xml").unlink()
        expected = "annotation XML not found"

    datalake = MagicMock()
    datalake.get_dataset_version.side_effect = RuntimeError("missing")

    with patch.object(pascal_voc, "_ensure_voc_schemas", return_value={}):
        with pytest.raises(FileNotFoundError, match=expected):
            pascal_voc.import_pascal_voc(
                datalake,
                pascal_voc.PascalVocImportConfig(
                    root_dir=tmp_path,
                    split="train",
                    dataset_name="tiny-pascal-voc-train",
                    show_progress=False,
                ),
            )


def test_import_pascal_voc_creates_classification_detection_and_segmentation_records(tmp_path: Path):
    build_tiny_voc_fixture(tmp_path)
    datalake = MagicMock()
    datalake.get_dataset_version.side_effect = RuntimeError("missing")
    datalake.create_asset_from_object.side_effect = [
        SimpleNamespace(asset_id="image_asset"),
        SimpleNamespace(asset_id="mask_asset"),
    ]
    datalake.create_datum.return_value = SimpleNamespace(datum_id="datum_1")
    datalake.create_annotation_set.side_effect = [
        SimpleNamespace(annotation_set_id="set_cls"),
        SimpleNamespace(annotation_set_id="set_det"),
        SimpleNamespace(annotation_set_id="set_seg"),
    ]
    datalake.create_dataset_version.return_value = SimpleNamespace(dataset_version_id="dataset_version_1")

    schemas = {
        "classification": make_schema_ref("schema_cls"),
        "detection": make_schema_ref("schema_det"),
        "segmentation": make_schema_ref("schema_seg"),
    }

    with patch.object(pascal_voc, "_ensure_voc_schemas", return_value=schemas):
        summary = pascal_voc.import_pascal_voc(
            datalake,
            pascal_voc.PascalVocImportConfig(
                root_dir=tmp_path,
                split="train",
                dataset_name="pascal-voc-2012-train",
                object_name_prefix="imports/pascal-voc-2012/demo/1.0.0",
                created_by="tester",
                show_progress=False,
            ),
        )

    assert summary.image_asset_count == 1
    assert summary.mask_asset_count == 1
    assert summary.classification_record_count == 1
    assert summary.detection_record_count == 1
    assert summary.segmentation_record_count == 1
    assert datalake.create_asset_from_object.call_count == 2
    assert datalake.create_asset_from_object.call_args_list[0].kwargs["on_conflict"] == "overwrite"
    assert datalake.create_asset_from_object.call_args_list[1].kwargs["kind"] == "mask"

    classification_records = datalake.add_annotation_records.call_args_list[0].args[0]
    detection_records = datalake.add_annotation_records.call_args_list[1].args[0]
    segmentation_records = datalake.add_annotation_records.call_args_list[2].args[0]

    assert classification_records[0]["kind"] == "classification"
    assert detection_records[0]["kind"] == "bbox"
    assert segmentation_records[0]["kind"] == "mask"
    assert segmentation_records[0]["geometry"]["mask_asset_id"] == "mask_asset"


def test_build_cli_parses_expected_arguments():
    parser = pascal_voc._build_cli()

    args = parser.parse_args(
        [
            "--mongo-db-uri",
            "mongodb://localhost:27017",
            "--mongo-db-name",
            "mindtrace",
            "--root-dir",
            "/tmp/voc",
            "--split",
            "val",
            "--dataset-name",
            "voc-val",
            "--dataset-version",
            "2.0.0",
            "--mount",
            "local",
            "--created-by",
            "tester",
            "--object-name-prefix",
            "imports/demo",
            "--download",
            "--source-url",
            "https://example.com/voc.tar",
            "--no-progress",
        ]
    )

    assert args.mongo_db_uri == "mongodb://localhost:27017"
    assert args.mongo_db_name == "mindtrace"
    assert args.root_dir == "/tmp/voc"
    assert args.split == "val"
    assert args.dataset_name == "voc-val"
    assert args.dataset_version == "2.0.0"
    assert args.mount == "local"
    assert args.created_by == "tester"
    assert args.object_name_prefix == "imports/demo"
    assert args.download is True
    assert args.source_url == "https://example.com/voc.tar"
    assert args.no_progress is True


def test_main_calls_importer_prints_summary_and_closes_datalake(capsys: pytest.CaptureFixture[str]):
    datalake = MagicMock()
    summary = pascal_voc.PascalVocImportSummary(
        dataset_name="tiny-pascal-voc-train",
        dataset_version="1.0.0",
        split="train",
        datum_count=1,
        image_asset_count=1,
        mask_asset_count=1,
        classification_record_count=1,
        detection_record_count=1,
        segmentation_record_count=1,
        dataset_version_id="dataset_version_1",
    )

    with (
        patch.object(pascal_voc.Datalake, "create", return_value=datalake),
        patch.object(pascal_voc, "import_pascal_voc", return_value=summary) as import_pascal_voc,
    ):
        exit_code = pascal_voc.main(
            [
                "--mongo-db-uri",
                "mongodb://localhost:27017",
                "--mongo-db-name",
                "mindtrace",
                "--root-dir",
                "/tmp/voc",
                "--split",
                "train",
            ]
        )

    assert exit_code == 0
    assert "Imported tiny-pascal-voc-train@1.0.0" in capsys.readouterr().out
    datalake.close.assert_called_once()
    import_pascal_voc.assert_called_once()


def test_main_entrypoint_executes_module(tmp_path: Path):
    build_tiny_voc_fixture(tmp_path)
    datalake = make_import_datalake_mock()
    argv = [
        "pascal_voc.py",
        "--mongo-db-uri",
        "mongodb://localhost:27017",
        "--mongo-db-name",
        "mindtrace",
        "--root-dir",
        str(tmp_path),
        "--split",
        "train",
        "--dataset-name",
        "tiny-pascal-voc-train",
        "--dataset-version",
        "1.0.0",
        "--no-progress",
    ]
    module_name = "mindtrace.datalake.importers.pascal_voc"
    original_module = sys.modules.pop(module_name, None)

    try:
        with (
            patch.object(sys, "argv", argv),
            patch("mindtrace.datalake.Datalake.create", return_value=datalake),
        ):
            with pytest.raises(SystemExit) as excinfo:
                runpy.run_module(module_name, run_name="__main__")
    finally:
        if original_module is not None:
            sys.modules[module_name] = original_module

    assert excinfo.value.code == 0
    datalake.close.assert_called_once()

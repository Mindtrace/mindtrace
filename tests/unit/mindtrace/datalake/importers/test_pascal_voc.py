from pathlib import Path
from unittest.mock import MagicMock, patch

from PIL import Image

from mindtrace.datalake.importers.pascal_voc import (
    PASCAL_VOC_SCHEMA_VERSION,
    PascalVocImportConfig,
    VOC_CLASS_TO_ID,
    _asset_object_name,
    _ensure_schema,
    _extract_present_segmentation_classes,
    _parse_detection_annotations,
    import_pascal_voc,
)
from mindtrace.datalake.types import AnnotationLabelDefinition, AnnotationSchema


def test_asset_object_name_is_flattened_for_local_registry_backend():
    name = _asset_object_name("imports/pascal-voc-2012/demo/1.0.0", "train", "images", "2008_000008.jpg")

    assert "/" not in name
    assert name.endswith("__train__images__2008_000008.jpg")


def test_parse_detection_annotations_converts_voc_bbox_xml(tmp_path: Path):
    annotation_path = tmp_path / "sample.xml"
    annotation_path.write_text(
        """
<annotation>
  <object>
    <name>person</name>
    <pose>Left</pose>
    <truncated>1</truncated>
    <difficult>0</difficult>
    <bndbox>
      <xmin>10</xmin>
      <ymin>20</ymin>
      <xmax>110</xmax>
      <ymax>220</ymax>
    </bndbox>
  </object>
</annotation>
""".strip()
    )

    records = _parse_detection_annotations(annotation_path)

    assert len(records) == 1
    record = records[0]
    assert record["label"] == "person"
    assert record["label_id"] == VOC_CLASS_TO_ID["person"]
    assert record["geometry"] == {"type": "bbox", "x": 10, "y": 20, "width": 100, "height": 200}
    assert record["attributes"]["pose"] == "Left"
    assert record["attributes"]["truncated"] == 1


def test_extract_present_segmentation_classes_builds_binary_masks(tmp_path: Path):
    mask_path = tmp_path / "mask.png"
    mask = Image.new("P", (2, 2))
    mask.putdata([0, VOC_CLASS_TO_ID["person"], VOC_CLASS_TO_ID["dog"], 255])
    mask.save(mask_path)

    extracted = _extract_present_segmentation_classes(mask_path)

    labels = [label for label, _ in extracted]
    assert labels == ["person", "dog"]

    person_mask = dict(extracted)["person"]
    assert list(person_mask.getdata()) == [0, 255, 0, 0]


def test_ensure_schema_updates_existing_schema_to_include_new_optional_attrs():
    datalake = MagicMock()
    existing = AnnotationSchema(
        name="pascal-voc-classification",
        version=PASCAL_VOC_SCHEMA_VERSION,
        task_type="classification",
        allowed_annotation_kinds=["classification"],
        labels=[AnnotationLabelDefinition(name="person", id=VOC_CLASS_TO_ID["person"])],
        optional_attributes=[],
    )
    updated = AnnotationSchema(
        name="pascal-voc-classification",
        version=PASCAL_VOC_SCHEMA_VERSION,
        task_type="classification",
        allowed_annotation_kinds=["classification"],
        labels=[AnnotationLabelDefinition(name="person", id=VOC_CLASS_TO_ID["person"])],
        optional_attributes=["layer"],
    )
    datalake.get_annotation_schema_by_name_version.return_value = existing
    datalake.update_annotation_schema.return_value = updated

    result = _ensure_schema(
        datalake,
        name="pascal-voc-classification",
        task_type="classification",
        allowed_annotation_kinds=["classification"],
        labels=[AnnotationLabelDefinition(name="person", id=VOC_CLASS_TO_ID["person"])],
        optional_attributes=["layer"],
    )

    datalake.update_annotation_schema.assert_called_once()
    assert result.optional_attributes == ["layer"]


def test_import_pascal_voc_uses_overwrite_for_importer_managed_payloads(tmp_path: Path):
    voc_root = tmp_path / "VOCdevkit" / "VOC2012"
    (voc_root / "JPEGImages").mkdir(parents=True)
    (voc_root / "Annotations").mkdir(parents=True)
    (voc_root / "ImageSets" / "Main").mkdir(parents=True)
    image_id = "2008_000008"
    Image.new("RGB", (4, 4), color=(0, 0, 0)).save(voc_root / "JPEGImages" / f"{image_id}.jpg")
    (voc_root / "Annotations" / f"{image_id}.xml").write_text("<annotation></annotation>")
    (voc_root / "ImageSets" / "Main" / "train.txt").write_text(f"{image_id}\n")

    datalake = MagicMock()
    datalake.get_dataset_version.side_effect = RuntimeError("missing")
    datalake.create_asset_from_object.return_value = MagicMock(asset_id="asset_1")
    datalake.create_datum.return_value = MagicMock(datum_id="datum_1")
    datalake.create_dataset_version.return_value = MagicMock(dataset_version_id="dataset_version_1")

    with patch("mindtrace.datalake.importers.pascal_voc._ensure_voc_schemas", return_value={}):
        summary = import_pascal_voc(
            datalake,
            PascalVocImportConfig(
                root_dir=tmp_path,
                split="train",
                dataset_name="pascal-voc-2012-train",
                download=False,
                show_progress=False,
            ),
        )

    assert summary.image_asset_count == 1
    datalake.create_asset_from_object.assert_called_once()
    assert datalake.create_asset_from_object.call_args.kwargs["on_conflict"] == "overwrite"

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from PIL import Image

from mindtrace.datalake.importers import pascal_voc

VOC_XML = """
<annotation>
  <object>
    <name>person</name>
    <pose>Left</pose>
    <truncated>0</truncated>
    <difficult>0</difficult>
    <bndbox>
      <xmin>1</xmin>
      <ymin>2</ymin>
      <xmax>5</xmax>
      <ymax>8</ymax>
    </bndbox>
  </object>
</annotation>
""".strip()


def build_tiny_voc_fixture(
    root: Path,
    *,
    split: str = "train",
    direct_root: bool = False,
    include_segmentation: bool = True,
    include_classification: bool = True,
    annotation_text: str = VOC_XML,
) -> tuple[Path, str]:
    """Create a tiny Pascal VOC-style fixture on disk."""

    voc_root = root / pascal_voc.PASCAL_VOC_2012_DIRNAME if direct_root else root / "VOCdevkit" / "VOC2012"
    (voc_root / "JPEGImages").mkdir(parents=True)
    (voc_root / "Annotations").mkdir(parents=True)
    (voc_root / "ImageSets" / "Main").mkdir(parents=True)

    image_id = "2008_000008"
    Image.new("RGB", (8, 8), color=(255, 0, 0)).save(voc_root / "JPEGImages" / f"{image_id}.jpg")
    (voc_root / "Annotations" / f"{image_id}.xml").write_text(annotation_text)
    (voc_root / "ImageSets" / "Main" / f"{split}.txt").write_text(f"{image_id}\n")

    if include_segmentation:
        (voc_root / "SegmentationClass").mkdir(parents=True, exist_ok=True)
        seg = Image.new("P", (2, 2))
        seg.putpalette([0] * (256 * 3))
        seg.putdata([0, pascal_voc.VOC_CLASS_TO_ID["person"], 0, 255])
        seg.save(voc_root / "SegmentationClass" / f"{image_id}.png")

    if include_classification:
        main_dir = voc_root / "ImageSets" / "Main"
        (main_dir / f"person_{split}.txt").write_text(f"{image_id} 1\n")
        for class_name in pascal_voc.VOC_CLASSES:
            if class_name == "person":
                continue
            (main_dir / f"{class_name}_{split}.txt").write_text(f"{image_id} -1\n")

    return voc_root, image_id


def make_schema_ref(annotation_schema_id: str) -> SimpleNamespace:
    """Return a lightweight schema object for importer tests."""

    return SimpleNamespace(annotation_schema_id=annotation_schema_id)


def make_import_datalake_mock() -> MagicMock:
    """Create a mock datalake configured for a full Pascal VOC import."""

    datalake = MagicMock()
    datalake.get_dataset_version.side_effect = RuntimeError("missing")
    datalake.get_annotation_schema_by_name_version.side_effect = RuntimeError("missing")

    schema_ids = iter(("schema_cls", "schema_det", "schema_seg"))
    datalake.create_annotation_schema.side_effect = lambda **_: make_schema_ref(next(schema_ids))

    asset_ids = iter(("image_asset", "mask_asset"))
    datalake.create_asset_from_object.side_effect = lambda **_: SimpleNamespace(asset_id=next(asset_ids))

    datalake.create_datum.return_value = SimpleNamespace(datum_id="datum_1")

    annotation_set_ids = iter(("set_cls", "set_det", "set_seg"))
    datalake.create_annotation_set.side_effect = lambda **_: SimpleNamespace(annotation_set_id=next(annotation_set_ids))

    datalake.create_dataset_version.return_value = SimpleNamespace(dataset_version_id="dataset_version_1")
    return datalake

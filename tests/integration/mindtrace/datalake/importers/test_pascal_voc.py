from pathlib import Path

from PIL import Image

from mindtrace.datalake import Datalake
from mindtrace.datalake.importers.pascal_voc import PascalVocImportConfig, import_pascal_voc


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


def _build_tiny_voc_fixture(root: Path) -> Path:
    voc_root = root / "VOCdevkit" / "VOC2012"
    (voc_root / "JPEGImages").mkdir(parents=True)
    (voc_root / "Annotations").mkdir(parents=True)
    (voc_root / "SegmentationClass").mkdir(parents=True)
    main_dir = voc_root / "ImageSets" / "Main"
    main_dir.mkdir(parents=True)

    image_id = "2008_000008"
    Image.new("RGB", (8, 8), color=(255, 0, 0)).save(voc_root / "JPEGImages" / f"{image_id}.jpg")
    (voc_root / "Annotations" / f"{image_id}.xml").write_text(VOC_XML)

    seg = Image.new("P", (2, 2))
    seg.putdata([0, 15, 0, 0])
    seg.save(voc_root / "SegmentationClass" / f"{image_id}.png")

    (main_dir / "train.txt").write_text(f"{image_id}\n")
    (main_dir / "person_train.txt").write_text(f"{image_id} 1\n")
    for class_name in [
        "aeroplane", "bicycle", "bird", "boat", "bottle", "bus", "car", "cat", "chair", "cow",
        "diningtable", "dog", "horse", "motorbike", "pottedplant", "sheep", "sofa", "train", "tvmonitor",
    ]:
        (main_dir / f"{class_name}_train.txt").write_text(f"{image_id} -1\n")

    return voc_root


def test_pascal_voc_importer_end_to_end_with_tiny_fixture(sync_datalake: Datalake, tmp_path: Path):
    _build_tiny_voc_fixture(tmp_path)

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

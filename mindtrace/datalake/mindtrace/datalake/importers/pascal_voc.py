from __future__ import annotations

import argparse
import tarfile
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Iterable

from PIL import Image
from tqdm import tqdm

from ..async_datalake import DuplicateAnnotationSchemaError
from ..datalake import Datalake
from ..types import AnnotationLabelDefinition, AnnotationSchema

PASCAL_VOC_2012_URL = "http://host.robots.ox.ac.uk/pascal/VOC/voc2012/VOCtrainval_11-May-2012.tar"
PASCAL_VOC_2012_ARCHIVE_NAME = "VOCtrainval_11-May-2012.tar"
PASCAL_VOC_2012_DIRNAME = "VOC2012"
PASCAL_VOC_SCHEMA_VERSION = "2012.1.0"
PASCAL_VOC_IMPORTER_VERSION = "1.0.0"
VOC_CLASSES = [
    "aeroplane",
    "bicycle",
    "bird",
    "boat",
    "bottle",
    "bus",
    "car",
    "cat",
    "chair",
    "cow",
    "diningtable",
    "dog",
    "horse",
    "motorbike",
    "person",
    "pottedplant",
    "sheep",
    "sofa",
    "train",
    "tvmonitor",
]
VOC_CLASS_TO_ID = {name: index + 1 for index, name in enumerate(VOC_CLASSES)}
VOC_SEGMENTATION_CLASS_TO_ID = {"background": 0, **VOC_CLASS_TO_ID}
VOC_SEGMENTATION_ID_TO_CLASS = {value: key for key, value in VOC_SEGMENTATION_CLASS_TO_ID.items()}


@dataclass(slots=True)
class PascalVocImportConfig:
    """Configuration for importing Pascal VOC 2012 into the Mindtrace Datalake."""

    root_dir: str | Path
    split: str
    dataset_name: str | None = None
    dataset_version: str = PASCAL_VOC_IMPORTER_VERSION
    download: bool = False
    mount: str | None = None
    created_by: str | None = None
    object_name_prefix: str | None = None
    source_url: str = PASCAL_VOC_2012_URL
    show_progress: bool = True


@dataclass(slots=True)
class PascalVocImportSummary:
    """Counts and identifiers produced during a Pascal VOC import."""

    dataset_name: str
    dataset_version: str
    split: str
    datum_count: int
    image_asset_count: int
    mask_asset_count: int
    classification_record_count: int
    detection_record_count: int
    segmentation_record_count: int
    dataset_version_id: str


def _default_dataset_name(split: str) -> str:
    return f"pascal-voc-2012-{split}"


def _normalize_root(root_dir: str | Path) -> Path:
    return Path(root_dir).expanduser().resolve()


def _voc_root_from_base(root_dir: Path) -> Path:
    direct = root_dir / PASCAL_VOC_2012_DIRNAME
    nested = root_dir / "VOCdevkit" / PASCAL_VOC_2012_DIRNAME
    if direct.exists():
        return direct
    if nested.exists():
        return nested
    return nested


def _download_if_missing(root_dir: Path, *, download: bool, source_url: str) -> Path:
    voc_root = _voc_root_from_base(root_dir)
    if voc_root.exists():
        return voc_root
    if not download:
        raise FileNotFoundError(
            f"Pascal VOC 2012 not found under {root_dir}. Expected {voc_root}. Pass download=True to fetch it."
        )

    root_dir.mkdir(parents=True, exist_ok=True)
    archive_path = root_dir / PASCAL_VOC_2012_ARCHIVE_NAME
    if not archive_path.exists():
        urllib.request.urlretrieve(source_url, archive_path)
    with tarfile.open(archive_path, "r") as tar:
        tar.extractall(path=root_dir)

    voc_root = _voc_root_from_base(root_dir)
    if not voc_root.exists():
        raise FileNotFoundError(f"Downloaded Pascal VOC archive, but could not find extracted directory at {voc_root}")
    return voc_root


def _ensure_required_layout(voc_root: Path) -> None:
    required = [
        voc_root / "JPEGImages",
        voc_root / "Annotations",
        voc_root / "ImageSets" / "Main",
    ]
    missing = [path for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Pascal VOC 2012 layout is incomplete. Missing: {', '.join(str(path) for path in missing)}")


def _read_split_ids(voc_root: Path, split: str) -> list[str]:
    split_path = voc_root / "ImageSets" / "Main" / f"{split}.txt"
    if not split_path.exists():
        raise FileNotFoundError(f"Pascal VOC split file not found: {split_path}")
    image_ids = [line.strip() for line in split_path.read_text().splitlines() if line.strip()]
    if not image_ids:
        raise ValueError(f"Pascal VOC split {split!r} is empty")
    return image_ids


def _read_classification_labels(voc_root: Path, split: str) -> dict[str, list[str]]:
    main_dir = voc_root / "ImageSets" / "Main"
    labels_by_image: dict[str, list[str]] = {}
    for class_name in VOC_CLASSES:
        path = main_dir / f"{class_name}_{split}.txt"
        if not path.exists():
            continue
        for line in path.read_text().splitlines():
            parts = line.split()
            if len(parts) != 2:
                continue
            image_id, label_flag = parts
            if int(label_flag) > 0:
                labels_by_image.setdefault(image_id, []).append(class_name)
    return labels_by_image


def _parse_detection_annotations(annotation_path: Path) -> list[dict]:
    tree = ET.parse(annotation_path)
    root = tree.getroot()
    annotations: list[dict] = []
    for obj in root.findall("object"):
        class_name = (obj.findtext("name") or "").strip()
        if class_name not in VOC_CLASS_TO_ID:
            continue
        bbox = obj.find("bndbox")
        if bbox is None:
            continue
        xmin = int(float(bbox.findtext("xmin", "0")))
        ymin = int(float(bbox.findtext("ymin", "0")))
        xmax = int(float(bbox.findtext("xmax", "0")))
        ymax = int(float(bbox.findtext("ymax", "0")))
        annotations.append(
            {
                "label": class_name,
                "label_id": VOC_CLASS_TO_ID[class_name],
                "geometry": {
                    "type": "bbox",
                    "x": xmin,
                    "y": ymin,
                    "width": max(0, xmax - xmin),
                    "height": max(0, ymax - ymin),
                },
                "attributes": {
                    "difficult": int(obj.findtext("difficult", "0") or 0),
                    "truncated": int(obj.findtext("truncated", "0") or 0),
                    "pose": (obj.findtext("pose") or "Unspecified").strip(),
                    "occluded": int(obj.findtext("occluded", "0") or 0),
                },
            }
        )
    return annotations


def _extract_present_segmentation_classes(mask_path: Path) -> list[tuple[str, Image.Image]]:
    with Image.open(mask_path) as mask_image:
        palette_image = mask_image.convert("P")
        pixels = list(palette_image.getdata())
        width, height = palette_image.size
        class_ids = sorted({value for value in pixels if value not in (0, 255) and value in VOC_SEGMENTATION_ID_TO_CLASS})
        masks: list[tuple[str, Image.Image]] = []
        for class_id in class_ids:
            class_name = VOC_SEGMENTATION_ID_TO_CLASS[class_id]
            binary = Image.new("L", (width, height))
            binary.putdata([255 if value == class_id else 0 for value in pixels])
            masks.append((class_name, binary))
        return masks


def _asset_object_name(prefix: str, split: str, kind: str, filename: str) -> str:
    return f"{prefix}/{split}/{kind}/{filename}"


def _schema_labels(include_background: bool = False) -> list[AnnotationLabelDefinition]:
    labels: list[AnnotationLabelDefinition] = []
    if include_background:
        labels.append(AnnotationLabelDefinition(name="background", id=0))
    labels.extend(AnnotationLabelDefinition(name=name, id=VOC_CLASS_TO_ID[name]) for name in VOC_CLASSES)
    return labels


def _ensure_schema(datalake: Datalake, *, name: str, task_type: str, allowed_annotation_kinds: list[str], labels: list[AnnotationLabelDefinition], required_attributes: list[str] | None = None, optional_attributes: list[str] | None = None) -> AnnotationSchema:
    try:
        return datalake.get_annotation_schema_by_name_version(name, PASCAL_VOC_SCHEMA_VERSION)
    except Exception:
        pass
    try:
        return datalake.create_annotation_schema(
            name=name,
            version=PASCAL_VOC_SCHEMA_VERSION,
            task_type=task_type,
            allowed_annotation_kinds=allowed_annotation_kinds,
            labels=labels,
            allow_scores=False,
            required_attributes=required_attributes or [],
            optional_attributes=optional_attributes or [],
            allow_additional_attributes=False,
            metadata={"source_dataset": "pascal_voc", "year": "2012"},
        )
    except DuplicateAnnotationSchemaError:
        return datalake.get_annotation_schema_by_name_version(name, PASCAL_VOC_SCHEMA_VERSION)


def _ensure_voc_schemas(datalake: Datalake) -> dict[str, AnnotationSchema]:
    return {
        "classification": _ensure_schema(
            datalake,
            name="pascal-voc-classification",
            task_type="classification",
            allowed_annotation_kinds=["classification"],
            labels=_schema_labels(),
        ),
        "detection": _ensure_schema(
            datalake,
            name="pascal-voc-detection",
            task_type="detection",
            allowed_annotation_kinds=["bbox"],
            labels=_schema_labels(),
            optional_attributes=["difficult", "truncated", "pose", "occluded"],
        ),
        "segmentation": _ensure_schema(
            datalake,
            name="pascal-voc-segmentation",
            task_type="segmentation",
            allowed_annotation_kinds=["mask"],
            labels=_schema_labels(),
        ),
    }


def _create_annotation_set_if_needed(datalake: Datalake, *, datum_id: str, name: str, annotation_schema_id: str):
    return datalake.create_annotation_set(
        name=name,
        purpose="ground_truth",
        source_type="human",
        status="active",
        datum_id=datum_id,
        annotation_schema_id=annotation_schema_id,
        metadata={"source_dataset": "pascal_voc", "year": "2012"},
    )


def _iter_segmentation_masks(mask_dir: Path, image_id: str) -> Iterable[tuple[str, Image.Image]]:
    mask_path = mask_dir / f"{image_id}.png"
    if not mask_path.exists():
        return []
    return _extract_present_segmentation_classes(mask_path)


def import_pascal_voc(datalake: Datalake, config: PascalVocImportConfig) -> PascalVocImportSummary:
    """Download, parse, and import Pascal VOC 2012 into the Mindtrace Datalake.

    The importer creates one image Asset and one Datum per sample, then attaches separate
    ground-truth annotation sets for classification, detection, and segmentation when data
    exists for that image. Segmentation is imported as one mask Asset and one mask annotation
    record per class present in the VOC segmentation class mask.
    """

    if config.split not in {"train", "val", "trainval"}:
        raise ValueError("Pascal VOC 2012 importer currently supports split in {'train', 'val', 'trainval'}")

    dataset_name = config.dataset_name or _default_dataset_name(config.split)
    root_dir = _normalize_root(config.root_dir)
    voc_root = _download_if_missing(root_dir, download=config.download, source_url=config.source_url)
    _ensure_required_layout(voc_root)

    try:
        datalake.get_dataset_version(dataset_name, config.dataset_version)
    except Exception:
        pass
    else:
        raise ValueError(f"Dataset version already exists: {dataset_name}@{config.dataset_version}")

    schemas = _ensure_voc_schemas(datalake)
    image_ids = _read_split_ids(voc_root, config.split)
    classification_labels = _read_classification_labels(voc_root, config.split)
    image_dir = voc_root / "JPEGImages"
    annotation_dir = voc_root / "Annotations"
    segmentation_mask_dir = voc_root / "SegmentationClass"
    object_prefix = config.object_name_prefix or f"imports/pascal-voc-2012/{dataset_name}/{config.dataset_version}"

    manifest: list[str] = []
    image_asset_count = 0
    mask_asset_count = 0
    classification_record_count = 0
    detection_record_count = 0
    segmentation_record_count = 0

    image_iterator = tqdm(image_ids, desc=f"Importing {dataset_name}", unit="image") if config.show_progress else image_ids

    for image_id in image_iterator:
        image_path = image_dir / f"{image_id}.jpg"
        annotation_path = annotation_dir / f"{image_id}.xml"
        if not image_path.exists():
            raise FileNotFoundError(f"Pascal VOC image not found: {image_path}")
        if not annotation_path.exists():
            raise FileNotFoundError(f"Pascal VOC annotation XML not found: {annotation_path}")

        image_bytes = image_path.read_bytes()
        image_asset = datalake.create_asset_from_object(
            name=_asset_object_name(object_prefix, config.split, "images", image_path.name),
            obj=image_bytes,
            kind="image",
            media_type="image/jpeg",
            mount=config.mount,
            object_metadata={
                "source_dataset": "pascal_voc",
                "year": "2012",
                "split": config.split,
                "source_path": str(image_path),
                "source_image_id": image_id,
            },
            asset_metadata={
                "source_dataset": "pascal_voc",
                "year": "2012",
                "split": config.split,
                "source_path": str(image_path),
                "source_image_id": image_id,
            },
            size_bytes=len(image_bytes),
            created_by=config.created_by,
        )
        image_asset_count += 1

        datum = datalake.create_datum(
            asset_refs={"image": image_asset.asset_id},
            split=config.split,
            metadata={
                "source_dataset": "pascal_voc",
                "year": "2012",
                "source_image_id": image_id,
            },
        )
        manifest.append(datum.datum_id)

        image_class_labels = sorted(set(classification_labels.get(image_id, [])))
        if image_class_labels:
            annotation_set = _create_annotation_set_if_needed(
                datalake,
                datum_id=datum.datum_id,
                name="pascal-voc-classification",
                annotation_schema_id=schemas["classification"].annotation_schema_id,
            )
            records = [
                {
                    "kind": "classification",
                    "label": class_name,
                    "label_id": VOC_CLASS_TO_ID[class_name],
                    "source": {"type": "human", "name": "pascal-voc", "version": "2012"},
                    "geometry": {},
                    "attributes": {"layer": "classification"},
                }
                for class_name in image_class_labels
            ]
            datalake.add_annotation_records(annotation_set.annotation_set_id, records)
            classification_record_count += len(records)

        detections = _parse_detection_annotations(annotation_path)
        if detections:
            annotation_set = _create_annotation_set_if_needed(
                datalake,
                datum_id=datum.datum_id,
                name="pascal-voc-detection",
                annotation_schema_id=schemas["detection"].annotation_schema_id,
            )
            records = [
                {
                    "kind": "bbox",
                    "label": detection["label"],
                    "label_id": detection["label_id"],
                    "source": {"type": "human", "name": "pascal-voc", "version": "2012"},
                    "geometry": detection["geometry"],
                    "attributes": detection["attributes"],
                }
                for detection in detections
            ]
            datalake.add_annotation_records(annotation_set.annotation_set_id, records)
            detection_record_count += len(records)

        segmentation_masks = list(_iter_segmentation_masks(segmentation_mask_dir, image_id))
        if segmentation_masks:
            annotation_set = _create_annotation_set_if_needed(
                datalake,
                datum_id=datum.datum_id,
                name="pascal-voc-segmentation",
                annotation_schema_id=schemas["segmentation"].annotation_schema_id,
            )
            records = []
            for class_name, binary_mask in segmentation_masks:
                mask_filename = f"{image_id}__{class_name}.png"
                mask_bytes = BytesIO()
                binary_mask.save(mask_bytes, format="PNG")
                mask_asset = datalake.create_asset_from_object(
                    name=_asset_object_name(object_prefix, config.split, "masks", mask_filename),
                    obj=mask_bytes.getvalue(),
                    kind="mask",
                    media_type="image/png",
                    mount=config.mount,
                    object_metadata={
                        "source_dataset": "pascal_voc",
                        "year": "2012",
                        "split": config.split,
                        "source_image_id": image_id,
                        "source_mask_type": "SegmentationClass",
                        "source_class_name": class_name,
                    },
                    asset_metadata={
                        "source_dataset": "pascal_voc",
                        "year": "2012",
                        "split": config.split,
                        "source_image_id": image_id,
                        "source_mask_type": "SegmentationClass",
                        "source_class_name": class_name,
                    },
                    created_by=config.created_by,
                )
                mask_asset_count += 1
                records.append(
                    {
                        "kind": "mask",
                        "label": class_name,
                        "label_id": VOC_CLASS_TO_ID[class_name],
                        "source": {"type": "human", "name": "pascal-voc", "version": "2012"},
                        "geometry": {"type": "mask", "mask_asset_id": mask_asset.asset_id},
                        "attributes": {"layer": "segmentation", "source_mask": "SegmentationClass"},
                    }
                )
            datalake.add_annotation_records(annotation_set.annotation_set_id, records)
            segmentation_record_count += len(records)

    dataset_version = datalake.create_dataset_version(
        dataset_name=dataset_name,
        version=config.dataset_version,
        manifest=manifest,
        metadata={
            "source_dataset": "pascal_voc",
            "year": "2012",
            "split": config.split,
            "importer": "mindtrace.datalake.importers.pascal_voc",
        },
        created_by=config.created_by,
    )
    return PascalVocImportSummary(
        dataset_name=dataset_name,
        dataset_version=config.dataset_version,
        split=config.split,
        datum_count=len(manifest),
        image_asset_count=image_asset_count,
        mask_asset_count=mask_asset_count,
        classification_record_count=classification_record_count,
        detection_record_count=detection_record_count,
        segmentation_record_count=segmentation_record_count,
        dataset_version_id=dataset_version.dataset_version_id,
    )


def _build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download and import Pascal VOC 2012 into the Mindtrace Datalake")
    parser.add_argument("--mongo-db-uri", required=True, help="MongoDB URI for the Mindtrace Datalake")
    parser.add_argument("--mongo-db-name", required=True, help="MongoDB database name for the Mindtrace Datalake")
    parser.add_argument("--root-dir", required=True, help="Directory that contains or will contain VOCdevkit/VOC2012")
    parser.add_argument("--split", choices=["train", "val", "trainval"], default="train")
    parser.add_argument("--dataset-name", help="Target dataset name in the Mindtrace Datalake")
    parser.add_argument("--dataset-version", default=PASCAL_VOC_IMPORTER_VERSION)
    parser.add_argument("--mount", help="Optional registry mount for imported image and mask assets")
    parser.add_argument("--created-by", help="Optional created_by field for imported rows")
    parser.add_argument("--object-name-prefix", help="Optional object-name prefix for imported assets")
    parser.add_argument("--download", action="store_true", help="Download Pascal VOC 2012 if it is missing locally")
    parser.add_argument("--source-url", default=PASCAL_VOC_2012_URL)
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable the tqdm progress bar during per-image import",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_cli()
    args = parser.parse_args(argv)

    datalake = Datalake.create(mongo_db_uri=args.mongo_db_uri, mongo_db_name=args.mongo_db_name)
    try:
        summary = import_pascal_voc(
            datalake,
            PascalVocImportConfig(
                root_dir=args.root_dir,
                split=args.split,
                dataset_name=args.dataset_name,
                dataset_version=args.dataset_version,
                download=args.download,
                mount=args.mount,
                created_by=args.created_by,
                object_name_prefix=args.object_name_prefix,
                source_url=args.source_url,
                show_progress=not args.no_progress,
            ),
        )
    finally:
        datalake.close()

    print(
        "Imported "
        f"{summary.dataset_name}@{summary.dataset_version} "
        f"({summary.split}) with {summary.datum_count} datums, "
        f"{summary.image_asset_count} image assets, {summary.mask_asset_count} mask assets, "
        f"{summary.classification_record_count} classification records, "
        f"{summary.detection_record_count} detection records, "
        f"and {summary.segmentation_record_count} segmentation records."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

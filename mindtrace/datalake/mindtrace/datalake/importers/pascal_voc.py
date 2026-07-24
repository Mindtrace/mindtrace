from __future__ import annotations

import argparse
import tarfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from tqdm import tqdm

from mindtrace.core.utils.download import download_with_progress

from ..async_datalake import DuplicateAnnotationSchemaError
from ..datalake import Datalake
from ..types import AnnotationLabelDefinition, AnnotationSchema

PASCAL_VOC_2012_URL = "http://host.robots.ox.ac.uk/pascal/VOC/voc2012/VOCtrainval_11-May-2012.tar"
PASCAL_VOC_2012_ARCHIVE_NAME = "VOCtrainval_11-May-2012.tar"
PASCAL_VOC_2012_DIRNAME = "VOC2012"
PASCAL_VOC_SCHEMA_VERSION = "2012.2.0"
PASCAL_VOC_IMPORTER_VERSION = "1.2.0"
VOC_TASKS = ("classification", "detection", "semantic_segmentation")
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
    tasks: tuple[str, ...] = VOC_TASKS
    create_task_versions: bool = True


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
    derived_datum_count: int
    dataset_names: dict[str, str]
    dataset_version_ids: dict[str, str]


def _default_dataset_name(split: str) -> str:
    return f"pascal-voc-2012-{split}"


def _dataset_view_names(dataset_name: str, tasks: tuple[str, ...]) -> dict[str, str]:
    names = {"canonical": dataset_name}
    if "classification" in tasks:
        names["classification_multi_label"] = f"{dataset_name}-classification-multi-label"
    if "detection" in tasks:
        names["detection"] = f"{dataset_name}-detection"
        names["classification_single_label"] = f"{dataset_name}-classification-single-label"
    if "semantic_segmentation" in tasks:
        names["semantic_segmentation"] = f"{dataset_name}-semantic-segmentation"
    return names


def _ensure_dataset_versions_absent(
    datalake: Datalake,
    dataset_names: dict[str, str],
    dataset_version: str,
) -> None:
    existing: list[str] = []
    for dataset_name in dataset_names.values():
        try:
            datalake.get_dataset_version(dataset_name, dataset_version)
        except Exception:
            continue
        existing.append(f"{dataset_name}@{dataset_version}")
    if existing:
        raise ValueError(f"Dataset version already exists for one or more views: {', '.join(existing)}")


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


def _download_archive(source_url: str, archive_path: Path, *, show_progress: bool) -> None:
    if show_progress:
        download_with_progress(source_url, archive_path, desc=f"Downloading {archive_path.name}")
    else:
        from urllib.request import urlretrieve

        urlretrieve(source_url, archive_path)


def _safe_extract_tar(archive_path: Path, root_dir: Path) -> None:
    try:
        with tarfile.open(archive_path, "r") as tar:
            tar.extractall(path=root_dir, filter="data")
    except TypeError:
        with tarfile.open(archive_path, "r") as tar:
            tar.extractall(path=root_dir)


def _download_if_missing(root_dir: Path, *, download: bool, source_url: str, show_progress: bool) -> Path:
    voc_root = _voc_root_from_base(root_dir)
    if voc_root.exists():
        return voc_root
    if not download:
        raise FileNotFoundError(
            f"Pascal VOC 2012 not found under {root_dir}. Expected {voc_root}. Pass download=True to fetch it."
        )

    root_dir.mkdir(parents=True, exist_ok=True)
    archive_path = root_dir / PASCAL_VOC_2012_ARCHIVE_NAME

    attempts = 2
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            if not archive_path.exists():
                _download_archive(source_url, archive_path, show_progress=show_progress)
            _safe_extract_tar(archive_path, root_dir)
            voc_root = _voc_root_from_base(root_dir)
            if not voc_root.exists():
                raise FileNotFoundError(
                    f"Downloaded Pascal VOC archive, but could not find extracted directory at {voc_root}"
                )
            return voc_root
        except (tarfile.TarError, EOFError, OSError) as exc:
            last_error = exc
            if archive_path.exists():
                archive_path.unlink()
            if attempt == attempts:
                break

    raise RuntimeError(
        f"Failed to download/extract Pascal VOC 2012 after {attempts} attempts; last error: {last_error}"
    ) from last_error


def _ensure_required_layout(voc_root: Path, tasks: tuple[str, ...] = VOC_TASKS) -> None:
    required = [voc_root / "JPEGImages"]
    if {"classification", "detection"} & set(tasks):
        required.append(voc_root / "ImageSets" / "Main")
    if "detection" in tasks:
        required.append(voc_root / "Annotations")
    if "semantic_segmentation" in tasks:
        required.extend([voc_root / "ImageSets" / "Segmentation", voc_root / "SegmentationClass"])
    missing = [path for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError(
            f"Pascal VOC 2012 layout is incomplete. Missing: {', '.join(str(path) for path in missing)}"
        )


def _read_split_ids(voc_root: Path, split: str, *, task: str = "detection") -> list[str]:
    split_group = "Segmentation" if task == "semantic_segmentation" else "Main"
    split_path = voc_root / "ImageSets" / split_group / f"{split}.txt"
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


def _asset_object_name(prefix: str, split: str, kind: str, filename: str) -> str:
    """Build a flat registry object name.

    The current local/temp registry backend does not safely handle slash-delimited object names,
    so we flatten importer-managed keys while preserving the original source path in metadata.
    """
    safe_prefix = prefix.replace("/", "__")
    return f"{safe_prefix}__{split}__{kind}__{filename}"


def _schema_labels(include_background: bool = False) -> list[AnnotationLabelDefinition]:
    labels: list[AnnotationLabelDefinition] = []
    if include_background:
        labels.append(AnnotationLabelDefinition(name="background", id=0))
    labels.extend(AnnotationLabelDefinition(name=name, id=VOC_CLASS_TO_ID[name]) for name in VOC_CLASSES)
    return labels


def _ensure_schema(
    datalake: Datalake,
    *,
    name: str,
    task_type: str,
    allowed_annotation_kinds: list[str],
    labels: list[AnnotationLabelDefinition],
    required_attributes: list[str] | None = None,
    optional_attributes: list[str] | None = None,
) -> AnnotationSchema:
    required_attributes = required_attributes or []
    optional_attributes = optional_attributes or []
    try:
        existing = datalake.get_annotation_schema_by_name_version(name, PASCAL_VOC_SCHEMA_VERSION)
        desired_optional = sorted(set(existing.optional_attributes) | set(optional_attributes))
        desired_required = sorted(set(existing.required_attributes) | set(required_attributes))
        desired_kinds = list(dict.fromkeys([*existing.allowed_annotation_kinds, *allowed_annotation_kinds]))
        if (
            existing.task_type != task_type
            or desired_optional != sorted(existing.optional_attributes)
            or desired_required != sorted(existing.required_attributes)
            or desired_kinds != list(existing.allowed_annotation_kinds)
        ):
            existing = datalake.update_annotation_schema(
                existing.annotation_schema_id,
                task_type=task_type,
                allowed_annotation_kinds=desired_kinds,
                required_attributes=desired_required,
                optional_attributes=desired_optional,
            )
        return existing
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
            required_attributes=required_attributes,
            optional_attributes=optional_attributes,
            allow_additional_attributes=False,
            metadata={"source_dataset": "pascal_voc", "year": "2012"},
        )
    except DuplicateAnnotationSchemaError:
        return datalake.get_annotation_schema_by_name_version(name, PASCAL_VOC_SCHEMA_VERSION)


def _ensure_voc_schemas(
    datalake: Datalake,
    tasks: tuple[str, ...] = VOC_TASKS,
) -> dict[str, AnnotationSchema]:
    schemas: dict[str, AnnotationSchema] = {}
    if "classification" in tasks:
        schemas["classification"] = _ensure_schema(
            datalake,
            name="pascal-voc-classification",
            task_type="classification",
            allowed_annotation_kinds=["classification"],
            labels=_schema_labels(),
            optional_attributes=["layer"],
        )
    if "detection" in tasks:
        schemas["detection"] = _ensure_schema(
            datalake,
            name="pascal-voc-detection",
            task_type="detection",
            allowed_annotation_kinds=["bbox"],
            labels=_schema_labels(),
            optional_attributes=["difficult", "truncated", "pose", "occluded"],
        )
    if "semantic_segmentation" in tasks:
        schemas["semantic_segmentation"] = _ensure_schema(
            datalake,
            name="pascal-voc-segmentation",
            task_type="segmentation",
            allowed_annotation_kinds=["mask"],
            labels=[AnnotationLabelDefinition(name="semantic_mask"), *_schema_labels(include_background=True)],
            required_attributes=["encoding", "ignore_index"],
            optional_attributes=["source_mask"],
        )
    return schemas


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


def import_pascal_voc(datalake: Datalake, config: PascalVocImportConfig) -> PascalVocImportSummary:
    """Download, parse, and import Pascal VOC 2012 into the Mindtrace Datalake.

    The importer creates each source image Asset once, attaches all requested annotations to
    one canonical Datum, and optionally creates task-specific DatasetVersion views over those
    shared Datums. Single-label classification uses lightweight region Datums that reference
    the source image Asset rather than storing cropped copies. Semantic segmentation preserves
    the original categorical VOC mask, including background ``0`` and void/ignore ``255`` pixels.
    """

    if config.split not in {"train", "val", "trainval"}:
        raise ValueError("Pascal VOC 2012 importer currently supports split in {'train', 'val', 'trainval'}")
    tasks = tuple(dict.fromkeys(config.tasks))
    unsupported_tasks = sorted(set(tasks) - set(VOC_TASKS))
    if unsupported_tasks:
        raise ValueError(f"Unsupported Pascal VOC task(s): {unsupported_tasks}; supported tasks: {list(VOC_TASKS)}")
    if not tasks:
        raise ValueError("Pascal VOC import requires at least one task")

    dataset_name = config.dataset_name or _default_dataset_name(config.split)
    root_dir = _normalize_root(config.root_dir)
    voc_root = _download_if_missing(
        root_dir,
        download=config.download,
        source_url=config.source_url,
        show_progress=config.show_progress,
    )
    _ensure_required_layout(voc_root, tasks)

    dataset_names = (
        _dataset_view_names(dataset_name, tasks) if config.create_task_versions else {"canonical": dataset_name}
    )
    _ensure_dataset_versions_absent(datalake, dataset_names, config.dataset_version)

    schemas = _ensure_voc_schemas(datalake, tasks)
    split_task = "semantic_segmentation" if tasks == ("semantic_segmentation",) else "detection"
    image_ids = _read_split_ids(voc_root, config.split, task=split_task)
    classification_labels = _read_classification_labels(voc_root, config.split) if "classification" in tasks else {}
    image_dir = voc_root / "JPEGImages"
    annotation_dir = voc_root / "Annotations"
    segmentation_mask_dir = voc_root / "SegmentationClass"
    object_prefix = config.object_name_prefix or f"imports/pascal-voc-2012/{dataset_name}/{config.dataset_version}"

    manifest: list[str] = []
    semantic_manifest: list[str] = []
    single_label_manifest: list[str] = []
    image_asset_count = 0
    mask_asset_count = 0
    classification_record_count = 0
    detection_record_count = 0
    segmentation_record_count = 0

    image_iterator = (
        tqdm(image_ids, desc=f"Importing {dataset_name}", unit="image") if config.show_progress else image_ids
    )

    for image_id in image_iterator:
        image_path = image_dir / f"{image_id}.jpg"
        annotation_path = annotation_dir / f"{image_id}.xml"
        if not image_path.exists():
            raise FileNotFoundError(f"Pascal VOC image not found: {image_path}")
        if "detection" in tasks and not annotation_path.exists():
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

        asset_refs = {"image": image_asset.asset_id}
        semantic_mask_asset = None
        if "semantic_segmentation" in tasks:
            mask_path = segmentation_mask_dir / f"{image_id}.png"
            if mask_path.exists():
                mask_bytes = mask_path.read_bytes()
                semantic_mask_asset = datalake.create_asset_from_object(
                    name=_asset_object_name(object_prefix, config.split, "semantic_masks", mask_path.name),
                    obj=mask_bytes,
                    kind="mask",
                    media_type="image/png",
                    mount=config.mount,
                    object_metadata={
                        "source_dataset": "pascal_voc",
                        "year": "2012",
                        "split": config.split,
                        "source_image_id": image_id,
                        "source_mask_type": "SegmentationClass",
                        "mask_encoding": "class_id",
                        "background_id": 0,
                        "ignore_index": 255,
                    },
                    asset_metadata={
                        "source_dataset": "pascal_voc",
                        "year": "2012",
                        "split": config.split,
                        "source_image_id": image_id,
                        "source_mask_type": "SegmentationClass",
                        "mask_encoding": "class_id",
                        "background_id": 0,
                        "ignore_index": 255,
                    },
                    size_bytes=len(mask_bytes),
                    created_by=config.created_by,
                )
                asset_refs["semantic_mask"] = semantic_mask_asset.asset_id
                mask_asset_count += 1
            elif tasks == ("semantic_segmentation",):
                raise FileNotFoundError(f"Pascal VOC semantic mask not found: {mask_path}")

        datum = datalake.create_datum(
            asset_refs=asset_refs,
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
            datalake.add_annotation_records(records, annotation_set_id=annotation_set.annotation_set_id)
            classification_record_count += len(records)

        detections = _parse_detection_annotations(annotation_path) if "detection" in tasks else []
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
            datalake.add_annotation_records(records, annotation_set_id=annotation_set.annotation_set_id)
            detection_record_count += len(records)

            if config.create_task_versions:
                for object_index, detection in enumerate(detections):
                    region_datum = datalake.create_datum(
                        asset_refs={"image": image_asset.asset_id},
                        split=config.split,
                        metadata={
                            "source_dataset": "pascal_voc",
                            "year": "2012",
                            "source_image_id": image_id,
                            "source_datum_id": datum.datum_id,
                            "source_object_index": object_index,
                            "source_bbox": [detection["geometry"][key] for key in ("x", "y", "width", "height")],
                            "derivation": "bbox_crop",
                        },
                    )
                    single_label_manifest.append(region_datum.datum_id)
                    region_annotation_set = _create_annotation_set_if_needed(
                        datalake,
                        datum_id=region_datum.datum_id,
                        name="pascal-voc-single-label-classification-source",
                        annotation_schema_id=schemas["detection"].annotation_schema_id,
                    )
                    datalake.add_annotation_records(
                        [
                            {
                                "kind": "bbox",
                                "label": detection["label"],
                                "label_id": detection["label_id"],
                                "source": {
                                    "type": "derived",
                                    "name": "pascal-voc-bbox-crop",
                                    "version": "2012",
                                },
                                "geometry": detection["geometry"],
                                "attributes": detection["attributes"],
                            }
                        ],
                        annotation_set_id=region_annotation_set.annotation_set_id,
                    )

        if semantic_mask_asset is not None:
            annotation_set = _create_annotation_set_if_needed(
                datalake,
                datum_id=datum.datum_id,
                name="pascal-voc-segmentation",
                annotation_schema_id=schemas["semantic_segmentation"].annotation_schema_id,
            )
            records = [
                {
                    "kind": "mask",
                    "label": "semantic_mask",
                    "source": {"type": "human", "name": "pascal-voc", "version": "2012"},
                    "geometry": {"type": "mask", "mask_asset_id": semantic_mask_asset.asset_id},
                    "attributes": {
                        "encoding": "class_id",
                        "ignore_index": 255,
                        "source_mask": "SegmentationClass",
                    },
                }
            ]
            datalake.add_annotation_records(records, annotation_set_id=annotation_set.annotation_set_id)
            segmentation_record_count += 1
            semantic_manifest.append(datum.datum_id)

    dataset_metadata = {
        "source_dataset": "pascal_voc",
        "year": "2012",
        "split": config.split,
        "importer": "mindtrace.datalake.importers.pascal_voc",
        "task_types": list(tasks),
    }
    if "classification" in tasks:
        dataset_metadata.update(
            {
                "classification_type": "multi_label",
                "classification_class_names": VOC_CLASSES,
            }
        )
    if "detection" in tasks:
        dataset_metadata.update(
            {
                "detection_class_names": VOC_CLASSES,
                "detection_bbox_format": "xywh",
                "detection_bbox_coordinates": "pixels",
            }
        )
    if "semantic_segmentation" in tasks:
        dataset_metadata.update(
            {
                "semantic_segmentation_class_names": ["background", *VOC_CLASSES],
                "semantic_segmentation_background_id": 0,
                "semantic_segmentation_ignore_index": 255,
                "semantic_segmentation_mask_encoding": "class_id",
            }
        )

    version_specs: dict[str, tuple[list[str], dict]] = {
        "canonical": (manifest, dataset_metadata),
    }
    if config.create_task_versions and "classification" in tasks:
        version_specs["classification_multi_label"] = (
            manifest,
            {
                **dataset_metadata,
                "task_type": "classification",
                "task_types": ["classification"],
                "classification_type": "multi_label",
            },
        )
    if config.create_task_versions and "detection" in tasks:
        version_specs["detection"] = (
            manifest,
            {
                **dataset_metadata,
                "task_type": "detection",
                "task_types": ["detection"],
            },
        )
        version_specs["classification_single_label"] = (
            single_label_manifest,
            {
                **dataset_metadata,
                "task_type": "classification",
                "task_types": ["classification"],
                "classification_type": "single_label",
                "classification_source": "bbox_crops",
                "source_dataset_name": dataset_name,
            },
        )
    if config.create_task_versions and "semantic_segmentation" in tasks:
        version_specs["semantic_segmentation"] = (
            semantic_manifest,
            {
                **dataset_metadata,
                "task_type": "semantic_segmentation",
                "task_types": ["semantic_segmentation"],
            },
        )

    dataset_version_ids: dict[str, str] = {}
    for view_name, (view_manifest, view_metadata) in version_specs.items():
        dataset_version = datalake.create_dataset_version(
            dataset_name=dataset_names[view_name],
            version=config.dataset_version,
            manifest=view_manifest,
            metadata=view_metadata,
            created_by=config.created_by,
        )
        dataset_version_ids[view_name] = dataset_version.dataset_version_id
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
        dataset_version_id=dataset_version_ids["canonical"],
        derived_datum_count=len(single_label_manifest),
        dataset_names=dataset_names,
        dataset_version_ids=dataset_version_ids,
    )


def _build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download and import Pascal VOC 2012 into the Mindtrace Datalake")
    parser.add_argument("--mongo-db-uri", required=True, help="MongoDB URI for the Mindtrace Datalake")
    parser.add_argument("--mongo-db-name", required=True, help="MongoDB database name for the Mindtrace Datalake")
    parser.add_argument("--root-dir", required=True, help="Directory that contains or will contain VOCdevkit/VOC2012")
    parser.add_argument("--split", choices=["train", "val", "trainval"], default="train")
    parser.add_argument("--dataset-name", help="Target dataset name in the Mindtrace Datalake")
    parser.add_argument("--dataset-version", default=PASCAL_VOC_IMPORTER_VERSION)
    parser.add_argument(
        "--task",
        action="append",
        choices=VOC_TASKS,
        help="Task to import; repeat for multiple tasks. Defaults to all VOC tasks.",
    )
    parser.add_argument("--mount", help="Optional registry mount for imported image and mask assets")
    parser.add_argument("--created-by", help="Optional created_by field for imported rows")
    parser.add_argument("--object-name-prefix", help="Optional object-name prefix for imported assets")
    parser.add_argument(
        "--no-task-versions",
        action="store_true",
        help="Create only the canonical all-task DatasetVersion.",
    )
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
                tasks=tuple(args.task or VOC_TASKS),
                create_task_versions=not args.no_task_versions,
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
        f"{summary.segmentation_record_count} segmentation records, and "
        f"{summary.derived_datum_count} derived region datums across "
        f"{len(summary.dataset_version_ids)} dataset versions."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

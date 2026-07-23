from __future__ import annotations

import argparse
import mimetypes
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from tqdm import tqdm

from ..async_datalake import DuplicateAnnotationSchemaError
from ..datalake import Datalake
from ..types import AnnotationLabelDefinition, AnnotationSchema

FLOWERS102_DATASET_NAME = "flowers-102"
FLOWERS102_SCHEMA_NAME = "flowers-102-classification"
FLOWERS102_SCHEMA_VERSION = "1.0.0"
FLOWERS102_IMPORTER_VERSION = "1.0.0"
FLOWERS102_SPLITS = ("train", "val", "test")
FLOWERS102_CLASS_COUNT = 102


@dataclass(slots=True)
class Flowers102ImportConfig:
    """Configuration for importing Oxford Flowers102 through torchvision."""

    root_dir: str | Path
    dataset_name: str = FLOWERS102_DATASET_NAME
    dataset_version: str = FLOWERS102_IMPORTER_VERSION
    splits: tuple[str, ...] = FLOWERS102_SPLITS
    download: bool = False
    mount: str | None = None
    created_by: str | None = None
    object_name_prefix: str | None = None
    show_progress: bool = True


@dataclass(slots=True)
class Flowers102ImportSummary:
    """Counts and identifiers produced during a Flowers102 import."""

    dataset_name: str
    dataset_version: str
    splits: tuple[str, ...]
    datum_count: int
    image_asset_count: int
    classification_record_count: int
    split_counts: dict[str, int] = field(default_factory=dict)
    dataset_version_id: str = ""


def _load_flowers102_dataset(root_dir: Path, split: str, *, download: bool):
    try:
        from torchvision.datasets import Flowers102
    except ImportError as exc:
        raise ImportError(
            "Flowers102 import requires the optional torchvision and scipy dependencies. "
            "Install mindtrace-datalake[import-flowers102]."
        ) from exc
    return Flowers102(root=root_dir, split=split, download=download)


def _validate_splits(splits: Iterable[str]) -> tuple[str, ...]:
    normalized = tuple(dict.fromkeys(splits))
    if not normalized:
        raise ValueError("Flowers102 import requires at least one split")
    unsupported = sorted(set(normalized) - set(FLOWERS102_SPLITS))
    if unsupported:
        raise ValueError(
            f"Unsupported Flowers102 split(s): {unsupported}. Supported splits: {list(FLOWERS102_SPLITS)}."
        )
    return normalized


def _dataset_image_paths(dataset: Any) -> list[Path]:
    image_files = getattr(dataset, "_image_files", None)
    if image_files is None:
        raise RuntimeError(
            "The installed torchvision Flowers102 dataset does not expose source image paths via '_image_files'."
        )
    return [Path(path) for path in image_files]


def _dataset_targets(dataset: Any) -> list[int]:
    labels = getattr(dataset, "_labels", None)
    if labels is None:
        labels = getattr(dataset, "targets", None)
    if labels is None:
        raise RuntimeError("The installed torchvision Flowers102 dataset does not expose classification targets.")
    return [int(label) for label in labels]


def _class_names(dataset: Any) -> list[str]:
    classes = getattr(dataset, "classes", None)
    if classes is not None and len(classes) == FLOWERS102_CLASS_COUNT:
        return [str(name) for name in classes]
    return [f"flower_{class_id:03d}" for class_id in range(FLOWERS102_CLASS_COUNT)]


def _ensure_schema(datalake: Datalake, class_names: list[str]) -> AnnotationSchema:
    try:
        existing = datalake.get_annotation_schema_by_name_version(
            FLOWERS102_SCHEMA_NAME,
            FLOWERS102_SCHEMA_VERSION,
        )
    except Exception:
        existing = None
    if existing is not None:
        return existing

    try:
        return datalake.create_annotation_schema(
            name=FLOWERS102_SCHEMA_NAME,
            version=FLOWERS102_SCHEMA_VERSION,
            task_type="classification",
            allowed_annotation_kinds=["classification"],
            labels=[
                AnnotationLabelDefinition(name=class_name, id=class_id)
                for class_id, class_name in enumerate(class_names)
            ],
            allow_scores=False,
            allow_additional_attributes=False,
            metadata={
                "source_dataset": "oxford-flowers-102",
                "class_count": FLOWERS102_CLASS_COUNT,
                "label_index_base": 0,
            },
        )
    except DuplicateAnnotationSchemaError:
        return datalake.get_annotation_schema_by_name_version(
            FLOWERS102_SCHEMA_NAME,
            FLOWERS102_SCHEMA_VERSION,
        )


def _asset_object_name(prefix: str, split: str, filename: str) -> str:
    safe_prefix = prefix.replace("/", "__")
    return f"{safe_prefix}__{split}__images__{filename}"


def _media_type(path: Path) -> str:
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def import_flowers102(datalake: Datalake, config: Flowers102ImportConfig) -> Flowers102ImportSummary:
    """Import selected Flowers102 splits into one immutable Datalake dataset version."""

    splits = _validate_splits(config.splits)
    root_dir = Path(config.root_dir).expanduser().resolve()

    try:
        datalake.get_dataset_version(config.dataset_name, config.dataset_version)
    except Exception:
        pass
    else:
        raise ValueError(f"Dataset version already exists: {config.dataset_name}@{config.dataset_version}")

    source_datasets = {
        split: _load_flowers102_dataset(root_dir, split, download=config.download) for split in splits
    }
    first_dataset = source_datasets[splits[0]]
    class_names = _class_names(first_dataset)
    schema = _ensure_schema(datalake, class_names)
    object_prefix = config.object_name_prefix or (
        f"imports/flowers-102/{config.dataset_name}/{config.dataset_version}"
    )

    manifest: list[str] = []
    split_counts: dict[str, int] = {}
    image_asset_count = 0
    classification_record_count = 0

    for split, source_dataset in source_datasets.items():
        image_paths = _dataset_image_paths(source_dataset)
        targets = _dataset_targets(source_dataset)
        if len(image_paths) != len(targets):
            raise ValueError(
                f"Flowers102 split {split!r} has {len(image_paths)} images but {len(targets)} targets."
            )
        if _class_names(source_dataset) != class_names:
            raise ValueError(f"Flowers102 class metadata differs between imported splits; mismatch found in {split!r}.")

        samples = zip(image_paths, targets, strict=True)
        if config.show_progress:
            samples = tqdm(samples, total=len(image_paths), desc=f"Importing {config.dataset_name}:{split}", unit="image")

        split_count = 0
        for source_index, (image_path, label_id) in enumerate(samples):
            if not 0 <= label_id < len(class_names):
                raise ValueError(f"Flowers102 target {label_id} is outside the expected 0..101 range.")
            if not image_path.is_file():
                raise FileNotFoundError(f"Flowers102 image not found: {image_path}")

            image_bytes = image_path.read_bytes()
            source_image_id = image_path.stem
            provenance = {
                "source_dataset": "oxford-flowers-102",
                "split": split,
                "source_index": source_index,
                "source_image_id": source_image_id,
                "source_filename": image_path.name,
                "label_id": label_id,
                "label_name": class_names[label_id],
            }
            image_asset = datalake.create_asset_from_object(
                name=_asset_object_name(object_prefix, split, image_path.name),
                obj=image_bytes,
                kind="image",
                media_type=_media_type(image_path),
                mount=config.mount,
                object_metadata=provenance,
                asset_metadata=provenance,
                size_bytes=len(image_bytes),
                created_by=config.created_by,
                on_conflict="overwrite",
            )
            image_asset_count += 1

            datum = datalake.create_datum(
                asset_refs={"image": image_asset.asset_id},
                split=split,
                metadata=provenance,
            )
            manifest.append(datum.datum_id)

            annotation_set = datalake.create_annotation_set(
                name=FLOWERS102_SCHEMA_NAME,
                purpose="ground_truth",
                source_type="human",
                status="active",
                datum_id=datum.datum_id,
                annotation_schema_id=schema.annotation_schema_id,
                metadata={"source_dataset": "oxford-flowers-102", "split": split},
            )
            datalake.add_annotation_records(
                [
                    {
                        "kind": "classification",
                        "label": class_names[label_id],
                        "label_id": label_id,
                        "source": {
                            "type": "human",
                            "name": "oxford-flowers-102",
                            "version": "1.0",
                        },
                        "geometry": {},
                        "attributes": {"split": split},
                    }
                ],
                annotation_set_id=annotation_set.annotation_set_id,
            )
            classification_record_count += 1
            split_count += 1
        split_counts[split] = split_count

    dataset_version = datalake.create_dataset_version(
        dataset_name=config.dataset_name,
        version=config.dataset_version,
        manifest=manifest,
        description="Oxford 102 Flowers image classification dataset",
        metadata={
            "source_dataset": "oxford-flowers-102",
            "task_type": "classification",
            "splits": list(splits),
            "class_count": len(class_names),
            "class_names": class_names,
            "label_index_base": 0,
            "importer": "mindtrace.datalake.importers.flowers102",
        },
        created_by=config.created_by,
    )
    return Flowers102ImportSummary(
        dataset_name=config.dataset_name,
        dataset_version=config.dataset_version,
        splits=splits,
        datum_count=len(manifest),
        image_asset_count=image_asset_count,
        classification_record_count=classification_record_count,
        split_counts=split_counts,
        dataset_version_id=dataset_version.dataset_version_id,
    )


def _build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download and import Flowers102 into the Mindtrace Datalake")
    parser.add_argument("--mongo-db-uri", required=True, help="MongoDB URI for the Mindtrace Datalake")
    parser.add_argument("--mongo-db-name", required=True, help="MongoDB database name for the Mindtrace Datalake")
    parser.add_argument("--root-dir", required=True, help="Directory containing or receiving Flowers102")
    parser.add_argument("--splits", nargs="+", choices=FLOWERS102_SPLITS, default=list(FLOWERS102_SPLITS))
    parser.add_argument("--dataset-name", default=FLOWERS102_DATASET_NAME)
    parser.add_argument("--dataset-version", default=FLOWERS102_IMPORTER_VERSION)
    parser.add_argument("--mount", help="Optional registry mount for imported images")
    parser.add_argument("--created-by", help="Optional created_by field for imported rows")
    parser.add_argument("--object-name-prefix", help="Optional object-name prefix for imported assets")
    parser.add_argument("--download", action="store_true", help="Download Flowers102 if it is missing locally")
    parser.add_argument("--no-progress", action="store_true", help="Disable the tqdm progress bar")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_cli().parse_args(argv)
    datalake = Datalake.create(mongo_db_uri=args.mongo_db_uri, mongo_db_name=args.mongo_db_name)
    try:
        summary = import_flowers102(
            datalake,
            Flowers102ImportConfig(
                root_dir=args.root_dir,
                dataset_name=args.dataset_name,
                dataset_version=args.dataset_version,
                splits=tuple(args.splits),
                download=args.download,
                mount=args.mount,
                created_by=args.created_by,
                object_name_prefix=args.object_name_prefix,
                show_progress=not args.no_progress,
            ),
        )
    finally:
        datalake.close()
    print(
        f"Imported {summary.dataset_name}@{summary.dataset_version}: "
        f"{summary.datum_count} datums across {summary.split_counts}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

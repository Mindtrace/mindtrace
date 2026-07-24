from __future__ import annotations

import argparse
import hashlib
import mimetypes
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image
from tqdm import tqdm

from mindtrace.core.utils.download import download_with_progress
from mindtrace.database.core.exceptions import DocumentNotFoundError

from ..async_datalake import DuplicateAnnotationSchemaError
from ..datalake import Datalake
from ..types import AnnotationLabelDefinition, AnnotationSchema

PENN_FUDAN_DATASET_NAME = "penn-fudan-ped"
PENN_FUDAN_SCHEMA_NAME = "penn-fudan-instance-segmentation"
PENN_FUDAN_SCHEMA_VERSION = "1.0.0"
PENN_FUDAN_IMPORTER_VERSION = "1.0.0"
PENN_FUDAN_ARCHIVE_NAME = "PennFudanPed.zip"
PENN_FUDAN_DIRNAME = "PennFudanPed"
PENN_FUDAN_SOURCE_URL = "https://www.cis.upenn.edu/~jshi/ped_html/PennFudanPed.zip"
PENN_FUDAN_CLASS_NAMES = ("background", "person")


@dataclass(slots=True)
class PennFudanImportConfig:
    """Configuration for importing Penn-Fudan pedestrian instance masks."""

    root_dir: str | Path
    dataset_name: str = PENN_FUDAN_DATASET_NAME
    dataset_version: str = PENN_FUDAN_IMPORTER_VERSION
    download: bool = False
    val_fraction: float = 0.2
    split_seed: int = 0
    mount: str | None = None
    created_by: str | None = None
    object_name_prefix: str | None = None
    show_progress: bool = True
    source_url: str = PENN_FUDAN_SOURCE_URL


@dataclass(slots=True)
class PennFudanImportSummary:
    """Counts and identifiers produced during a Penn-Fudan import."""

    dataset_name: str
    dataset_version: str
    splits: tuple[str, ...]
    datum_count: int
    image_asset_count: int
    mask_asset_count: int
    instance_record_count: int
    split_counts: dict[str, int] = field(default_factory=dict)
    dataset_version_id: str = ""


@dataclass(frozen=True, slots=True)
class _Instance:
    instance_id: int
    bbox_xywh: tuple[int, int, int, int]
    area: int


def _penn_fudan_root(root_dir: Path) -> Path:
    direct = root_dir / PENN_FUDAN_DIRNAME
    if direct.exists():
        return direct
    if root_dir.name == PENN_FUDAN_DIRNAME and root_dir.exists():
        return root_dir
    return direct


def _safe_extract_zip(archive_path: Path, root_dir: Path) -> None:
    root = root_dir.resolve()
    with zipfile.ZipFile(archive_path) as archive:
        for member in archive.infolist():
            destination = (root / member.filename).resolve()
            if destination != root and root not in destination.parents:
                raise ValueError(f"Unsafe path in Penn-Fudan archive: {member.filename!r}")
        archive.extractall(root)


def _download_if_missing(
    root_dir: Path,
    *,
    download: bool,
    source_url: str,
    show_progress: bool,
) -> Path:
    dataset_root = _penn_fudan_root(root_dir)
    if dataset_root.exists():
        return dataset_root
    if not download:
        raise FileNotFoundError(
            f"Penn-Fudan not found under {root_dir}. Expected {dataset_root}. Pass download=True to fetch it."
        )
    root_dir.mkdir(parents=True, exist_ok=True)
    archive_path = root_dir / PENN_FUDAN_ARCHIVE_NAME
    if not archive_path.exists():
        if show_progress:
            download_with_progress(source_url, archive_path, desc=f"Downloading {archive_path.name}")
        else:
            from urllib.request import urlretrieve

            urlretrieve(source_url, archive_path)
    _safe_extract_zip(archive_path, root_dir)
    dataset_root = _penn_fudan_root(root_dir)
    if not dataset_root.exists():
        raise FileNotFoundError(f"Downloaded Penn-Fudan archive did not contain {PENN_FUDAN_DIRNAME}.")
    return dataset_root


def _sample_paths(dataset_root: Path) -> list[tuple[Path, Path]]:
    image_dir = dataset_root / "PNGImages"
    mask_dir = dataset_root / "PedMasks"
    if not image_dir.is_dir() or not mask_dir.is_dir():
        raise FileNotFoundError(
            f"Penn-Fudan layout is incomplete under {dataset_root}; expected PNGImages/ and PedMasks/."
        )
    image_paths = sorted(image_dir.glob("*.png"))
    if not image_paths:
        raise ValueError(f"Penn-Fudan contains no PNG images under {image_dir}.")
    samples: list[tuple[Path, Path]] = []
    for image_path in image_paths:
        mask_path = mask_dir / f"{image_path.stem}_mask.png"
        if not mask_path.is_file():
            raise FileNotFoundError(f"Penn-Fudan mask not found for {image_path.name}: {mask_path}")
        samples.append((image_path, mask_path))
    return samples


def _split_assignments(
    image_paths: list[Path],
    *,
    val_fraction: float,
    split_seed: int,
) -> dict[str, str]:
    if not 0 <= val_fraction < 1:
        raise ValueError("Penn-Fudan val_fraction must be in the range [0, 1).")
    ranked = sorted(
        image_paths,
        key=lambda path: hashlib.sha256(f"{split_seed}:{path.name}".encode()).hexdigest(),
    )
    val_count = round(len(ranked) * val_fraction)
    if val_fraction > 0 and len(ranked) > 1:
        val_count = max(1, min(val_count, len(ranked) - 1))
    val_names = {path.name for path in ranked[:val_count]}
    return {path.name: ("val" if path.name in val_names else "train") for path in image_paths}


def _instances_from_mask(mask_path: Path) -> list[_Instance]:
    with Image.open(mask_path) as mask:
        if mask.mode not in {"L", "P", "I"}:
            raise ValueError(
                f"Penn-Fudan mask {mask_path} must be an indexed single-channel PNG; received mode {mask.mode!r}."
            )
        width, height = mask.size
        bounds: dict[int, list[int]] = {}
        areas: dict[int, int] = {}
        for offset, raw_value in enumerate(mask.getdata()):
            instance_id = int(raw_value)
            if instance_id == 0:
                continue
            x = offset % width
            y = offset // width
            if instance_id not in bounds:
                bounds[instance_id] = [x, y, x, y]
                areas[instance_id] = 0
            box = bounds[instance_id]
            box[0] = min(box[0], x)
            box[1] = min(box[1], y)
            box[2] = max(box[2], x)
            box[3] = max(box[3], y)
            areas[instance_id] += 1
    return [
        _Instance(
            instance_id=instance_id,
            bbox_xywh=(box[0], box[1], box[2] - box[0] + 1, box[3] - box[1] + 1),
            area=areas[instance_id],
        )
        for instance_id, box in sorted(bounds.items())
    ]


def _validate_schema(schema: AnnotationSchema) -> AnnotationSchema:
    labels = [(label.id, label.name) for label in schema.labels]
    if (
        schema.task_type != "instance_segmentation"
        or "instance_mask" not in schema.allowed_annotation_kinds
        or labels != [(1, "person")]
    ):
        raise ValueError(f"Existing annotation schema {schema.name}@{schema.version} is incompatible with Penn-Fudan.")
    return schema


def _ensure_schema(datalake: Datalake) -> AnnotationSchema:
    try:
        existing = datalake.get_annotation_schema_by_name_version(
            PENN_FUDAN_SCHEMA_NAME,
            PENN_FUDAN_SCHEMA_VERSION,
        )
    except DocumentNotFoundError:
        pass
    else:
        return _validate_schema(existing)
    try:
        return datalake.create_annotation_schema(
            name=PENN_FUDAN_SCHEMA_NAME,
            version=PENN_FUDAN_SCHEMA_VERSION,
            task_type="instance_segmentation",
            allowed_annotation_kinds=["instance_mask"],
            labels=[AnnotationLabelDefinition(name="person", id=1)],
            allow_scores=False,
            allow_additional_attributes=True,
            metadata={
                "source_dataset": "penn-fudan-ped",
                "class_names": list(PENN_FUDAN_CLASS_NAMES),
                "background_id": 0,
            },
        )
    except DuplicateAnnotationSchemaError:
        return _validate_schema(
            datalake.get_annotation_schema_by_name_version(
                PENN_FUDAN_SCHEMA_NAME,
                PENN_FUDAN_SCHEMA_VERSION,
            )
        )


def _object_name(prefix: str, role: str, filename: str) -> str:
    return f"{prefix.replace('/', '__')}__{role}__{filename}"


def _media_type(path: Path) -> str:
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def import_penn_fudan(datalake: Datalake, config: PennFudanImportConfig) -> PennFudanImportSummary:
    """Import Penn-Fudan as one split-aware instance-segmentation DatasetVersion."""

    root_dir = Path(config.root_dir).expanduser().resolve()
    try:
        datalake.get_dataset_version(config.dataset_name, config.dataset_version)
    except DocumentNotFoundError:
        pass
    else:
        raise ValueError(f"Dataset version already exists: {config.dataset_name}@{config.dataset_version}")

    dataset_root = _download_if_missing(
        root_dir,
        download=config.download,
        source_url=config.source_url,
        show_progress=config.show_progress,
    )
    samples = _sample_paths(dataset_root)
    assignments = _split_assignments(
        [image_path for image_path, _ in samples],
        val_fraction=config.val_fraction,
        split_seed=config.split_seed,
    )
    schema = _ensure_schema(datalake)
    prefix = config.object_name_prefix or f"imports/penn-fudan/{config.dataset_name}/{config.dataset_version}"

    manifest: list[str] = []
    split_counts: dict[str, int] = {}
    instance_record_count = 0
    iterable = tqdm(samples, desc=f"Importing {config.dataset_name}", unit="image") if config.show_progress else samples
    for image_path, mask_path in iterable:
        split = assignments[image_path.name]
        instances = _instances_from_mask(mask_path)
        if not instances:
            raise ValueError(f"Penn-Fudan mask contains no pedestrian instances: {mask_path}")
        image_bytes = image_path.read_bytes()
        mask_bytes = mask_path.read_bytes()
        provenance = {
            "source_dataset": "penn-fudan-ped",
            "source_image_id": image_path.stem,
            "source_filename": image_path.name,
            "source_mask_filename": mask_path.name,
            "split": split,
            "split_seed": config.split_seed,
            "val_fraction": config.val_fraction,
            "instance_count": len(instances),
        }
        image_asset = datalake.create_asset_from_object(
            name=_object_name(prefix, "images", image_path.name),
            obj=image_bytes,
            kind="image",
            media_type=_media_type(image_path),
            mount=config.mount,
            object_metadata=provenance,
            asset_metadata=provenance,
            size_bytes=len(image_bytes),
            created_by=config.created_by,
        )
        mask_asset = datalake.create_asset_from_object(
            name=_object_name(prefix, "instance_masks", mask_path.name),
            obj=mask_bytes,
            kind="mask",
            media_type=_media_type(mask_path),
            mount=config.mount,
            object_metadata=provenance,
            asset_metadata=provenance,
            size_bytes=len(mask_bytes),
            created_by=config.created_by,
        )
        datum = datalake.create_datum(
            asset_refs={"image": image_asset.asset_id, "instance_mask": mask_asset.asset_id},
            split=split,
            metadata=provenance,
        )
        manifest.append(datum.datum_id)
        annotation_set = datalake.create_annotation_set(
            name=PENN_FUDAN_SCHEMA_NAME,
            purpose="ground_truth",
            source_type="human",
            status="active",
            datum_id=datum.datum_id,
            annotation_schema_id=schema.annotation_schema_id,
            metadata={"source_dataset": "penn-fudan-ped", "split": split},
        )
        datalake.add_annotation_records(
            [
                {
                    "kind": "instance_mask",
                    "label": "person",
                    "label_id": 1,
                    "source": {"type": "human", "name": "penn-fudan-ped", "version": "1.0"},
                    "geometry": {
                        "mask_asset_id": mask_asset.asset_id,
                        "instance_id": instance.instance_id,
                        "encoding": {"type": "indexed_png", "background_id": 0},
                    },
                    "attributes": {
                        "bbox_xywh": list(instance.bbox_xywh),
                        "area": instance.area,
                        "iscrowd": False,
                    },
                }
                for instance in instances
            ],
            annotation_set_id=annotation_set.annotation_set_id,
        )
        instance_record_count += len(instances)
        split_counts[split] = split_counts.get(split, 0) + 1

    splits = tuple(split for split in ("train", "val") if split in split_counts)
    dataset_version = datalake.create_dataset_version(
        dataset_name=config.dataset_name,
        version=config.dataset_version,
        manifest=manifest,
        description="Penn-Fudan pedestrian instance segmentation dataset",
        metadata={
            "source_dataset": "penn-fudan-ped",
            "task_type": "instance_segmentation",
            "task_types": ["instance_segmentation"],
            "instance_segmentation_class_names": list(PENN_FUDAN_CLASS_NAMES),
            "instance_segmentation_background_id": 0,
            "instance_segmentation_mask_encoding": "indexed_png",
            "splits": list(splits),
            "split_counts": split_counts,
            "split_strategy": "stable_filename_hash",
            "split_seed": config.split_seed,
            "val_fraction": config.val_fraction,
            "importer": "mindtrace.datalake.importers.penn_fudan",
        },
        created_by=config.created_by,
    )
    return PennFudanImportSummary(
        dataset_name=config.dataset_name,
        dataset_version=config.dataset_version,
        splits=splits,
        datum_count=len(manifest),
        image_asset_count=len(manifest),
        mask_asset_count=len(manifest),
        instance_record_count=instance_record_count,
        split_counts=split_counts,
        dataset_version_id=dataset_version.dataset_version_id,
    )


def _build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download and import Penn-Fudan into the Mindtrace Datalake")
    parser.add_argument("--mongo-db-uri", required=True)
    parser.add_argument("--mongo-db-name", required=True)
    parser.add_argument("--root-dir", required=True)
    parser.add_argument("--dataset-name", default=PENN_FUDAN_DATASET_NAME)
    parser.add_argument("--dataset-version", default=PENN_FUDAN_IMPORTER_VERSION)
    parser.add_argument("--val-fraction", type=float, default=0.2)
    parser.add_argument("--split-seed", type=int, default=0)
    parser.add_argument("--mount")
    parser.add_argument("--created-by")
    parser.add_argument("--object-name-prefix")
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--no-progress", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_cli().parse_args(argv)
    datalake = Datalake.create(mongo_db_uri=args.mongo_db_uri, mongo_db_name=args.mongo_db_name)
    try:
        summary = import_penn_fudan(
            datalake,
            PennFudanImportConfig(
                root_dir=args.root_dir,
                dataset_name=args.dataset_name,
                dataset_version=args.dataset_version,
                download=args.download,
                val_fraction=args.val_fraction,
                split_seed=args.split_seed,
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
        f"{summary.datum_count} images, {summary.instance_record_count} instances across {summary.split_counts}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

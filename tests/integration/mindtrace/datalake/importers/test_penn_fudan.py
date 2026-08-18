from pathlib import Path

from datasets import load_from_disk
from PIL import Image

from mindtrace.datalake import Datalake
from mindtrace.datalake.importers.penn_fudan import PennFudanImportConfig, import_penn_fudan


def _build_tiny_penn_fudan_fixture(root: Path) -> None:
    dataset_root = root / "PennFudanPed"
    image_dir = dataset_root / "PNGImages"
    mask_dir = dataset_root / "PedMasks"
    image_dir.mkdir(parents=True)
    mask_dir.mkdir(parents=True)
    Image.new("RGB", (3, 2), color="white").save(image_dir / "FudanPed00001.png")
    mask = Image.new("L", (3, 2))
    mask.putdata([0, 1, 1, 0, 2, 2])
    mask.save(mask_dir / "FudanPed00001_mask.png")


def test_penn_fudan_import_and_media_free_huggingface_export_preserve_instance_geometry(
    sync_datalake: Datalake,
    tmp_path: Path,
):
    _build_tiny_penn_fudan_fixture(tmp_path)
    summary = import_penn_fudan(
        sync_datalake,
        PennFudanImportConfig(
            root_dir=tmp_path,
            dataset_name="tiny-penn-fudan",
            dataset_version="1.0.0",
            val_fraction=0,
            show_progress=False,
        ),
    )
    destination = tmp_path / "export"

    sync_datalake.export_dataset_version_to_format(
        summary.dataset_name,
        summary.dataset_version,
        format="huggingface",
        destination=destination,
        include_media=False,
        exporter_options={"task": "instance_segmentation"},
    )
    exported = load_from_disk(str(destination))["train"]

    assert exported[0]["image"] is None
    assert exported[0]["objects"]["mask"] == [None, None]
    assert exported[0]["objects"]["bbox"] == [[1.0, 0.0, 2.0, 1.0], [1.0, 1.0, 2.0, 1.0]]
    assert exported[0]["objects"]["area"] == [2.0, 2.0]

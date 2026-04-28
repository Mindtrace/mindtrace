"""Unit tests for ``mindtrace.core.utils.image_io.ImageLoader``."""

from unittest.mock import MagicMock

import cv2
import numpy as np
import pytest

from mindtrace.core.utils.image_io import ImageLoader


def test_read_single_bgr_roundtrip(tmp_path) -> None:
    path = tmp_path / "x.png"
    cv2.imwrite(str(path), np.full((4, 4, 3), 33, dtype=np.uint8))
    loader = ImageLoader(num_workers=1, color_mode="bgr")
    key, arr = loader._read_single("k", str(path))
    assert key == "k"
    assert arr.shape == (4, 4, 3)


def test_read_single_rgb_swaps_channels(tmp_path) -> None:
    path = tmp_path / "c.png"
    # Pure blue in BGR
    bgr = np.zeros((2, 2, 3), dtype=np.uint8)
    bgr[:, :, 0] = 255
    cv2.imwrite(str(path), bgr)
    loader = ImageLoader(num_workers=1, color_mode="rgb")
    _, arr = loader._read_single("k", str(path))
    assert arr[0, 0, 2] == 255


def test_read_single_missing_file() -> None:
    loader = ImageLoader(num_workers=1)
    with pytest.raises(FileNotFoundError, match="not found"):
        loader._read_single("k", "/no/such/fileZZ.png")


def test_read_single_decode_failure(tmp_path) -> None:
    path = tmp_path / "bad.jpg"
    path.write_bytes(b"not an image")
    loader = ImageLoader(num_workers=1)
    with pytest.raises(ValueError, match="decode"):
        loader._read_single("k", str(path))


def test_init_rejects_bad_workers() -> None:
    with pytest.raises(ValueError, match="num_workers"):
        ImageLoader(num_workers=0)


def test_init_rejects_color_mode() -> None:
    with pytest.raises(ValueError, match="color_mode"):
        ImageLoader(num_workers=1, color_mode="xyz")  # type: ignore[arg-type]


def test_load_empty_mapping() -> None:
    loader = ImageLoader(num_workers=2)
    assert loader.load({}) == {}


def test_load_preserves_order_and_drops_failures(tmp_path) -> None:
    good = tmp_path / "g.png"
    cv2.imwrite(str(good), np.zeros((2, 2, 3), dtype=np.uint8))
    loader = ImageLoader(num_workers=2)
    loader.logger = MagicMock()
    out = loader.load({"a": str(good), "b": "/nope/missing.png"})
    assert list(out.keys()) == ["a"]
    loader.logger.exception.assert_called()


def test_load_batch_skips_failed_entries(tmp_path) -> None:
    good = tmp_path / "g.png"
    cv2.imwrite(str(good), np.zeros((2, 2, 3), dtype=np.uint8))
    loader = ImageLoader(num_workers=1)
    loader.logger = MagicMock()
    batch = loader.load_batch([str(good), "/bad/missing.png"])
    assert len(batch) == 1
    loader.logger.exception.assert_called()
    loader.logger.warning.assert_called()


def test_repr() -> None:
    assert "ImageLoader" in repr(ImageLoader(num_workers=3, color_mode="rgb"))

"""Unit tests for ``mindtrace.core.types.crop.Crop``."""

import numpy as np
import pytest

from mindtrace.core.types.bounding_box import BoundingBox
from mindtrace.core.types.crop import Crop


def test_crop_post_init_rejects_non_ndarray() -> None:
    bb = BoundingBox(0, 0, 10, 10)
    with pytest.raises(TypeError, match="numpy ndarray"):
        Crop(image=[[1, 2]], source_bbox=bb, source_key="k")  # type: ignore[arg-type]


def test_from_image_and_bbox_basic() -> None:
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    bb = BoundingBox(10, 20, 30, 40)
    crop = Crop.from_image_and_bbox(img, bb, source_key="cam1")
    assert crop.height == 40
    assert crop.width == 30
    assert crop.source_key == "cam1"
    assert crop.source_bbox == bb
    np.testing.assert_array_equal(crop.image, img[20:60, 10:40])


def test_from_image_and_bbox_with_padding_records_metadata() -> None:
    img = np.zeros((100, 100), dtype=np.uint8)
    bb = BoundingBox(40, 40, 20, 20)
    crop = Crop.from_image_and_bbox(img, bb, padding=0.5, source_key="s")
    assert crop.metadata.get("padding") == 0.5
    assert crop.image.size > 0


def test_from_image_and_bbox_empty_clip_raises() -> None:
    img = np.zeros((10, 10))
    bb = BoundingBox(100, 100, 5, 5)
    with pytest.raises(ValueError, match="empty"):
        Crop.from_image_and_bbox(img, bb)


def test_crop_eq_hash_repr() -> None:
    img = np.ones((5, 5), dtype=np.uint8)
    bb = BoundingBox(0, 0, 5, 5)
    a = Crop(image=img, source_bbox=bb, source_key="x", metadata={"k": 1})
    b = Crop(image=img.copy(), source_bbox=bb, source_key="x", metadata={"k": 1})
    assert a == b
    assert hash(a) == hash(b)
    assert a.__eq__("not a crop") is NotImplemented
    assert repr(a).startswith("Crop(")


def test_crop_eq_different_pixels() -> None:
    bb = BoundingBox(0, 0, 5, 5)
    a = Crop(image=np.zeros((5, 5)), source_bbox=bb, source_key="")
    b = Crop(image=np.ones((5, 5)), source_bbox=bb, source_key="")
    assert a != b

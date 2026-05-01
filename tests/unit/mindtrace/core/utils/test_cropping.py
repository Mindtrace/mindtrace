"""Unit tests for ``mindtrace.core.utils.cropping.CropExtractor``."""

import numpy as np
import pytest

from mindtrace.core.types.bounding_box import BoundingBox
from mindtrace.core.utils import cropping as cropping_mod
from mindtrace.core.utils.cropping import CropExtractor


def test_extractor_init_requires_numpy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cropping_mod, "_HAS_NUMPY", False)
    with pytest.raises(ImportError, match="numpy"):
        CropExtractor()


def test_make_square_shifts_when_negative_x() -> None:
    bbox = BoundingBox(-10.0, 40.0, 20.0, 10.0)
    sq = CropExtractor._make_square(bbox, img_w=100, img_h=100)
    assert sq.x >= 0


def test_make_square_shifts_when_overflow_right() -> None:
    bbox = BoundingBox(85.0, 40.0, 30.0, 10.0)
    sq = CropExtractor._make_square(bbox, img_w=100, img_h=100)
    assert sq.x + sq.width <= 100 + 1e-6


def test_make_square_shifts_when_negative_y() -> None:
    bbox = BoundingBox(40.0, -10.0, 10.0, 20.0)
    sq = CropExtractor._make_square(bbox, img_w=100, img_h=100)
    assert sq.y >= 0


def test_make_square_shifts_when_overflow_bottom() -> None:
    bbox = BoundingBox(40.0, 85.0, 10.0, 30.0)
    sq = CropExtractor._make_square(bbox, img_w=100, img_h=100)
    assert sq.y + sq.height <= 100 + 1e-6


def test_from_mask_skips_contours_below_min_area() -> None:
    img = np.zeros((30, 30))
    mask = np.zeros((30, 30), dtype=np.uint8)
    mask[10:11, 10:11] = 255
    crops = CropExtractor().from_mask(img, mask, min_area=500, source_key="x")
    assert crops == []


def test_extractor_init_negative_padding() -> None:
    with pytest.raises(ValueError, match="padding"):
        CropExtractor(padding=-0.1)


def test_from_bboxes_skips_empty_after_clip() -> None:
    img = np.zeros((50, 50))
    bboxes = [
        BoundingBox(10, 10, 10, 10),
        BoundingBox(100, 100, 10, 10),
    ]
    crops = CropExtractor().from_bboxes(img, bboxes)
    assert len(crops) == 1


def test_from_bboxes_square_makes_equal_hw() -> None:
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    bbox = BoundingBox(40, 40, 20, 10)
    ex = CropExtractor(padding=0.1, square=True)
    crops = ex.from_bboxes(img, [bbox], source_key="k")
    assert len(crops) == 1
    assert crops[0].metadata["square"] is True
    assert crops[0].height == crops[0].width


def test_make_square_clamps_to_image() -> None:
    bbox = BoundingBox(90, 10, 10, 10)
    sq = CropExtractor._make_square(bbox, img_w=100, img_h=100)
    assert sq.x + sq.width <= 100 + 1e-6
    assert sq.y + sq.height <= 100 + 1e-6


def test_from_mask_uint8_square_region() -> None:
    img = np.zeros((40, 40, 3), dtype=np.uint8)
    mask = np.zeros((40, 40), dtype=np.uint8)
    mask[10:20, 10:20] = 255
    crops = CropExtractor().from_mask(img, mask, min_area=10, source_key="m")
    assert len(crops) == 1
    assert crops[0].height == 10
    assert crops[0].width == 10


def test_from_mask_bool_dtype() -> None:
    img = np.zeros((20, 20))
    mask = np.zeros((20, 20), dtype=bool)
    mask[5:15, 5:15] = True
    crops = CropExtractor().from_mask(img, mask, source_key="x")
    assert len(crops) == 1


def test_from_mask_non_uint8_converts() -> None:
    img = np.zeros((15, 15))
    mask = np.zeros((15, 15), dtype=np.float32)
    mask[2:8, 2:8] = 1.0
    crops = CropExtractor().from_mask(img, mask, min_area=5, source_key="y")
    assert len(crops) >= 1


def test_from_mask_requires_cv2(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cropping_mod, "_HAS_CV2", False)
    with pytest.raises(ImportError, match="opencv"):
        CropExtractor().from_mask(
            np.zeros((5, 5)),
            np.zeros((5, 5), dtype=np.uint8),
        )


def test_repr() -> None:
    assert "0.05" in repr(CropExtractor(padding=0.05, square=False))

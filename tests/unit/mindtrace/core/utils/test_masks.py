"""Unit tests for ``mindtrace.core.utils.masks.MaskProcessor``."""

import numpy as np
import pytest
import torch

from mindtrace.core.types.bounding_box import BoundingBox
from mindtrace.core.utils import masks as masks_mod
from mindtrace.core.utils.masks import MaskProcessor


def test_logits_to_mask_requires_torch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(masks_mod, "_HAS_TORCH", False)
    with pytest.raises(ImportError, match="torch"):
        MaskProcessor.logits_to_mask(torch.zeros(1, 2, 2, 2))


def test_logits_to_mask_requires_numpy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(masks_mod, "_HAS_NUMPY", False)
    with pytest.raises(ImportError, match="numpy"):
        MaskProcessor.logits_to_mask(torch.zeros(1, 2, 2, 2))


def test_overlay_requires_numpy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(masks_mod, "_HAS_NUMPY", False)
    with pytest.raises(ImportError, match="numpy"):
        MaskProcessor.overlay(
            np.zeros((2, 2, 3), dtype=np.uint8),
            np.zeros((2, 2), dtype=np.int64),
        )


def test_combine_requires_numpy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(masks_mod, "_HAS_NUMPY", False)
    with pytest.raises(ImportError, match="numpy"):
        MaskProcessor.combine([np.zeros((2, 2), dtype=np.int64)])


def test_extract_contours_requires_numpy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(masks_mod, "_HAS_NUMPY", False)
    with pytest.raises(ImportError, match="numpy"):
        MaskProcessor.extract_contours(np.zeros((3, 3), dtype=np.uint8))


def test_extract_contours_requires_cv2(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(masks_mod, "_HAS_CV2", False)
    with pytest.raises(ImportError, match="cv2"):
        MaskProcessor.extract_contours(np.zeros((3, 3), dtype=np.uint8))


def test_logits_to_mask_three_d_no_batch() -> None:
    logits = torch.zeros(3, 8, 8)
    logits[1, 2:5, 2:5] = 5.0
    mask = MaskProcessor.logits_to_mask(logits)
    assert mask.shape == (8, 8)
    assert mask.dtype == np.int64


def test_logits_to_mask_four_d_keeps_batch() -> None:
    logits = torch.randn(2, 3, 4, 4)
    mask = MaskProcessor.logits_to_mask(logits)
    assert mask.shape == (2, 4, 4)


def test_logits_to_mask_target_size() -> None:
    logits = torch.randn(1, 2, 4, 4)
    mask = MaskProcessor.logits_to_mask(logits, target_size=(8, 8))
    assert mask.shape == (1, 8, 8)


def test_logits_to_mask_conf_threshold_background() -> None:
    logits = torch.zeros(1, 2, 2, 2)
    mask = MaskProcessor.logits_to_mask(logits, conf_threshold=0.99, background_class=0)
    assert np.all(mask == 0)


def test_logits_to_mask_num_classes_mismatch() -> None:
    logits = torch.zeros(1, 3, 2, 2)
    with pytest.raises(ValueError, match="Expected 2 classes"):
        MaskProcessor.logits_to_mask(logits, num_classes=2)


def test_logits_to_mask_bad_ndim() -> None:
    with pytest.raises(ValueError, match="3D"):
        MaskProcessor.logits_to_mask(torch.zeros(2, 3))


def test_overlay_resizes_mask_to_image() -> None:
    image = np.zeros((10, 10, 3), dtype=np.uint8)
    mask = np.zeros((5, 5), dtype=np.int64)
    mask[1:4, 1:4] = 1
    out = MaskProcessor.overlay(image, mask, alpha=0.5)
    assert out.shape == image.shape


def test_overlay_with_explicit_color_map() -> None:
    image = np.ones((4, 4, 3), dtype=np.uint8) * 200
    mask = np.array([[0, 1], [1, 0]], dtype=np.int64)
    cmap = {0: (0, 0, 0), 1: (255, 0, 0)}
    out = MaskProcessor.overlay(image, mask, color_map=cmap, alpha=1.0)
    assert out.shape == (4, 4, 3)


def test_combine_max_last_first() -> None:
    a = np.array([[0, 1], [0, 0]], dtype=np.int64)
    b = np.array([[2, 0], [0, 3]], dtype=np.int64)
    mx = MaskProcessor.combine([a, b], strategy="max")
    assert mx[0, 0] == 2
    assert mx[1, 1] == 3
    last = MaskProcessor.combine([a, b], strategy="last")
    assert last[0, 1] == 1
    assert last[1, 1] == 3
    first = MaskProcessor.combine([a, b], strategy="first")
    assert first[0, 1] == 1
    assert first[1, 1] == 3


def test_combine_empty_raises() -> None:
    with pytest.raises(ValueError, match="not be empty"):
        MaskProcessor.combine([])


def test_combine_shape_mismatch() -> None:
    with pytest.raises(ValueError, match="shape"):
        MaskProcessor.combine([np.zeros((2, 2)), np.zeros((3, 3))])


def test_combine_unknown_strategy() -> None:
    with pytest.raises(ValueError, match="Unknown strategy"):
        MaskProcessor.combine([np.zeros((2, 2))], strategy="nope")  # type: ignore[arg-type]


def test_extract_contours_and_bboxes() -> None:
    mask = np.zeros((20, 20), dtype=np.uint8)
    mask[5:15, 5:15] = 1
    contours = MaskProcessor.extract_contours(mask, min_area=10)
    assert len(contours) >= 1
    boxes = MaskProcessor.extract_bboxes(mask, min_area=10)
    assert len(boxes) >= 1
    assert isinstance(boxes[0], BoundingBox)


def test_extract_contours_filters_small() -> None:
    mask = np.zeros((30, 30), dtype=np.uint8)
    mask[1:2, 1:2] = 1
    assert MaskProcessor.extract_contours(mask, min_area=100) == []


def test_repr() -> None:
    assert "MaskProcessor" in repr(MaskProcessor())


def test_overlay_requires_cv2(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(masks_mod, "_HAS_CV2", False)
    with pytest.raises(ImportError, match="cv2"):
        MaskProcessor.overlay(
            np.zeros((2, 2, 3), dtype=np.uint8),
            np.zeros((2, 2), dtype=np.int64),
        )

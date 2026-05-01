"""Unit tests for ``mindtrace.core.utils.letterbox.LetterBox``."""

import numpy as np
import pytest

from mindtrace.core.utils import letterbox as letterbox_mod
from mindtrace.core.utils.letterbox import LetterBox


def test_init_requires_numpy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(letterbox_mod, "_HAS_NUMPY", False)
    with pytest.raises(ImportError, match="numpy"):
        LetterBox()


def test_init_requires_cv2(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(letterbox_mod, "_HAS_CV2", False)
    with pytest.raises(ImportError, match="cv2"):
        LetterBox()


def test_call_rejects_non_positive_dimensions() -> None:
    lb = LetterBox(new_shape=(64, 64))
    with pytest.raises(ValueError, match="positive"):
        lb(np.zeros((0, 10, 3), dtype=np.uint8))


def test_new_shape_int_square() -> None:
    lb = LetterBox(new_shape=32)
    img = np.zeros((16, 8, 3), dtype=np.uint8)
    out = lb(img)
    assert out.shape[0] == 32
    assert out.shape[1] == 32


def test_scale_up_false_only_downscales() -> None:
    lb = LetterBox(new_shape=(100, 100), scale_up=False)
    img = np.ones((10, 10, 3), dtype=np.uint8)
    out = lb(img)
    assert out.shape[0] == 100
    assert out.shape[1] == 100


def test_scale_fill_stretches() -> None:
    lb = LetterBox(new_shape=(40, 40), scale_fill=True, center=False)
    img = np.zeros((20, 10, 3), dtype=np.uint8)
    out = lb(img)
    assert out.shape[0] == 40
    assert out.shape[1] == 40


def test_auto_sets_stride_aligned_padding() -> None:
    lb = LetterBox(new_shape=(64, 64), auto=True, stride=32)
    img = np.ones((32, 32, 3), dtype=np.uint8)
    _ = lb(img)
    assert isinstance(lb.dw, float)
    assert isinstance(lb.dh, float)


def test_center_false_pads_bottom_right() -> None:
    lb = LetterBox(new_shape=(50, 50), center=False)
    img = np.ones((25, 25, 3), dtype=np.uint8)
    out = lb(img)
    assert out.shape[:2] == (50, 50)


def test_identity_resize_when_already_target() -> None:
    lb = LetterBox(new_shape=(10, 10))
    img = np.ones((10, 10, 3), dtype=np.uint8)
    out = lb(img)
    assert out.shape[:2] == (10, 10)


def test_grayscale_two_dimensions() -> None:
    lb = LetterBox(new_shape=(20, 20))
    img = np.ones((10, 10), dtype=np.uint8)
    out = lb(img)
    assert out.shape == (20, 20)


def test_repr_contains_config() -> None:
    s = repr(LetterBox(new_shape=(640, 640), auto=True))
    assert "LetterBox" in s
    assert "auto=True" in s

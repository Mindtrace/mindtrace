import math
import pytest
from PIL import Image

from mindtrace.core import check_libs
from mindtrace.core.types.rotated_rect import RotatedRect
from mindtrace.core.types.bounding_box import BoundingBox


def approx_tuple(t, p=1e-5):
    return pytest.approx(t[0], abs=p), pytest.approx(t[1], abs=p)


def test_basic_properties_and_as_tuple():
    rr = RotatedRect(100.0, 50.0, 40.0, 20.0, 30.0)
    assert rr.area() == pytest.approx(800.0)
    assert rr.as_tuple() == ((100.0, 50.0), (40.0, 20.0), 30.0)


def test_to_from_opencv_roundtrip():
    rr = RotatedRect(10.5, 20.5, 30.0, 15.0, -15.0)
    t = rr.to_opencv()
    rr2 = RotatedRect.from_opencv(t)
    assert rr2.as_tuple() == rr.as_tuple()


def test_to_corners_and_to_bounding_box_order_invariant():
    rr = RotatedRect(50.0, 40.0, 30.0, 10.0, 25.0)
    corners = rr.to_corners()
    assert len(corners) == 4
    # bounding box should enclose all corners
    bb = rr.to_bounding_box()
    for (x, y) in corners:
        assert bb.x <= x <= bb.x2
        assert bb.y <= y <= bb.y2


def test_contains_point_center_and_outside():
    rr = RotatedRect(100.0, 60.0, 40.0, 20.0, 45.0)
    assert rr.contains_point(100.0, 60.0)  # center
    assert not rr.contains_point(1000.0, 1000.0)


def test_draw_on_pil_changes_pixels_with_fill():
    img = Image.new("RGB", (200, 150), color=(255, 255, 255))
    rr = RotatedRect(100.0, 75.0, 60.0, 30.0, 30.0)
    img2 = rr.draw_on_pil(img, color=(0, 255, 0), width=2, fill=(255, 0, 0, 255), label="rot")
    assert isinstance(img2, Image.Image)
    # Sample pixel at center; should be filled (red-ish, not white)
    px = img2.getpixel((int(rr.cx), int(rr.cy)))
    assert px != (255, 255, 255)


def test_draw_on_pil_label_fallbacks(monkeypatch):
    img = Image.new("RGB", (100, 80), color=(255, 255, 255))
    rr = RotatedRect(20.0, 20.0, 10.0, 8.0, 15.0)
    # Force ImageFont.load_default to raise to cover except path
    monkeypatch.setattr("PIL.ImageFont.load_default", lambda: (_ for _ in ()).throw(Exception("err")))
    # Remove textbbox attribute to use textsize fallback
    import PIL.ImageDraw as ID

    if hasattr(ID.ImageDraw, "textbbox"):
        monkeypatch.delattr(ID.ImageDraw, "textbbox", raising=False)

    img2 = rr.draw_on_pil(img, label="r")
    assert isinstance(img2, Image.Image)


def test_draw_on_pil_label_font_metrics_branches_rotated(monkeypatch):
    img = Image.new("RGB", (120, 90), color=(255, 255, 255))
    rr = RotatedRect(40.0, 40.0, 20.0, 10.0, 10.0)

    import PIL.ImageDraw as ID
    if hasattr(ID.ImageDraw, "textbbox"):
        monkeypatch.delattr(ID.ImageDraw, "textbbox", raising=False)

    # Patch text to no-op to avoid default font loading
    monkeypatch.setattr(ID.ImageDraw, "text", lambda self, xy, text, fill=None, font=None: None, raising=False)

    class FontBBox:
        def getbbox(self, text):
            return (0, 0, 9 * len(text), 13)

    class FontSize:
        def getsize(self, text):
            return (10 * len(text), 14)

    # getbbox branch
    img_a = rr.draw_on_pil(img.copy(), label="ab", font=FontBBox())
    assert isinstance(img_a, Image.Image)
    # getsize branch
    img_b = rr.draw_on_pil(img.copy(), label="cd", font=FontSize())
    assert isinstance(img_b, Image.Image)
    # default dims branch (no getbbox or getsize)
    class DummyFont:
        pass

    img_c = rr.draw_on_pil(img.copy(), label="ef", font=DummyFont())
    assert isinstance(img_c, Image.Image)


@pytest.mark.parametrize("use_offset", [False, True])
def test_iou_numpy_guard_and_values(use_offset):
    missing_libs = check_libs(["numpy"])
    if missing_libs:
        pytest.skip(f"Required libraries not installed: {', '.join(missing_libs)}. Skipping test.")

    a = RotatedRect(100.0, 60.0, 40.0, 20.0, 30.0)
    if not use_offset:
        b = RotatedRect(100.0, 60.0, 40.0, 20.0, 30.0)
        assert a.iou(b) == pytest.approx(1.0)
    else:
        b = RotatedRect(105.0, 60.0, 40.0, 20.0, 30.0)
        iou_val = a.iou(b)
        assert 0.0 < iou_val < 1.0


def test_to_corners_np_and_orientation_normalization():
    missing_libs = check_libs(["numpy"])
    if missing_libs:
        pytest.skip(f"Required libraries not installed: {', '.join(missing_libs)}. Skipping test.")

    rr = RotatedRect(0, 0, 10, 5, 33)
    arr = rr.to_corners_np()
    assert arr.shape == (4, 2)
    # Confirm signed area is non-negative (CCW normalization)
    import numpy as np

    def signed_area(poly):
        x = poly[:, 0]
        y = poly[:, 1]
        return 0.5 * ((x * np.roll(y, -1) - y * np.roll(x, -1)).sum())

    assert signed_area(arr) >= 0


def test_to_corners_math_only_branch(monkeypatch):
    # Force math-only branch by disabling cv2
    import mindtrace.core.types.rotated_rect as rrmod

    monkeypatch.setattr(rrmod, "_HAS_CV2", False)
    rr = RotatedRect(10, 10, 8, 4, 20)
    corners = rr.to_corners()
    assert len(corners) == 4


def test_to_corners_np_raises_without_numpy(monkeypatch):
    import mindtrace.core.types.rotated_rect as rrmod

    monkeypatch.setattr(rrmod, "_HAS_NUMPY", False)
    with pytest.raises(ImportError):
        RotatedRect(0, 0, 10, 5, 0).to_corners_np()


def test_iou_raises_without_numpy(monkeypatch):
    import mindtrace.core.types.rotated_rect as rrmod

    monkeypatch.setattr(rrmod, "_HAS_NUMPY", False)
    with pytest.raises(ImportError):
        RotatedRect(0, 0, 10, 5, 0).iou(RotatedRect(0, 0, 10, 5, 0))


def test_iou_orientation_normalization_branches(monkeypatch):
    missing_libs = check_libs(["numpy"])
    if missing_libs:
        pytest.skip(f"Required libraries not installed: {', '.join(missing_libs)}. Skipping test.")

    import numpy as np

    # Craft CW-oriented rectangle polygon so signed area < 0
    cw_poly = np.array([[0.0, 0.0], [2.0, 0.0], [2.0, 1.0], [0.0, 1.0]], dtype=float)[::-1]

    # Monkeypatch to return CW for both a and b to trigger both reversals
    def fake_to_corners_np(self):
        return cw_poly.copy()

    monkeypatch.setattr(RotatedRect, "to_corners_np", fake_to_corners_np)

    a = RotatedRect(0, 0, 2, 1, 0)
    b = RotatedRect(0, 0, 2, 1, 0)
    # Since polygons are identical besides orientation, IoU should be 1.0 and both reversal branches are hit
    assert a.iou(b) == pytest.approx(1.0)


def test_iou_zero_for_disjoint_shapes():
    missing_libs = check_libs(["numpy"])
    if missing_libs:
        pytest.skip(f"Required libraries not installed: {', '.join(missing_libs)}. Skipping test.")

    a = RotatedRect(0, 0, 10, 5, 0)
    b = RotatedRect(100, 100, 10, 5, 0)
    assert a.iou(b) == 0.0


def test_intersection_parallel_fallback():
    missing_libs = check_libs(["numpy"])
    if missing_libs:
        pytest.skip(f"Required libraries not installed: {', '.join(missing_libs)}. Skipping test.")

    import numpy as np
    from mindtrace.core.types.rotated_rect import _intersection

    # Parallel lines: a-b and s-e both horizontal
    a = np.array([0.0, 0.0])
    b = np.array([1.0, 0.0])
    s = np.array([0.0, 1.0])
    e = np.array([1.0, 1.0])
    out = _intersection(s, e, a, b)
    assert np.allclose(out, s)


def test_polygon_area_small_polygon_returns_zero():
    missing_libs = check_libs(["numpy"])
    if missing_libs:
        pytest.skip(f"Required libraries not installed: {', '.join(missing_libs)}. Skipping test.")

    import numpy as np
    from mindtrace.core.types.rotated_rect import _polygon_area

    poly = np.array([[0.0, 0.0], [1.0, 0.0]])  # 2 points only
    assert _polygon_area(poly) == 0.0


def test_polygon_signed_area_small_polygon_returns_zero():
    missing_libs = check_libs(["numpy"])
    if missing_libs:
        pytest.skip(f"Required libraries not installed: {', '.join(missing_libs)}. Skipping test.")

    import numpy as np
    from mindtrace.core.types.rotated_rect import _polygon_signed_area

    # Less than 3 points -> should return 0.0
    assert _polygon_signed_area(np.array([], dtype=float).reshape(0, 2)) == 0.0
    assert _polygon_signed_area(np.array([[0.0, 0.0]], dtype=float)) == 0.0
    assert _polygon_signed_area(np.array([[0.0, 0.0], [1.0, 0.0]], dtype=float)) == 0.0 
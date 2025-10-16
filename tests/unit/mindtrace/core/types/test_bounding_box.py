import pytest
from PIL import Image

from mindtrace.core import check_libs
from mindtrace.core.types.bounding_box import BoundingBox


def test_basic_properties_and_area():
    bb = BoundingBox(10.0, 20.0, 30.0, 40.0)
    assert bb.x2 == pytest.approx(40.0)
    assert bb.y2 == pytest.approx(60.0)
    assert bb.right == pytest.approx(40.0)
    assert bb.bottom == pytest.approx(60.0)
    assert bb.area() == pytest.approx(1200.0)


def test_opencv_conversions_rounding():
    bb = BoundingBox(10.2, 20.7, 30.9, 40.4)
    assert bb.to_opencv_xywh() == (10, 21, 31, 40)
    assert bb.to_opencv_xyxy() == (10, 21, 41, 61)

    bb2 = BoundingBox.from_opencv_xywh(10, 20, 30, 40)
    assert bb2.as_tuple() == (10, 20, 30, 40)

    bb3 = BoundingBox.from_opencv_xyxy(10, 20, 40, 60)
    assert bb3.as_tuple() == (10, 20, 30, 40)


def test_opencv_conversions_float():
    bb = BoundingBox(1.5, 2.5, 3.5, 4.5)
    assert bb.to_opencv_xywh(as_int=False) == (1.5, 2.5, 3.5, 4.5)
    assert bb.to_opencv_xyxy(as_int=False) == (1.5, 2.5, 5.0, 7.0)


def test_geometry_translate_scale_clip_contains():
    bb = BoundingBox(5, 5, 10, 10)
    moved = bb.translate(3, -2)
    assert moved.as_tuple() == (8, 3, 10, 10)

    scaled = bb.scale(2)
    assert scaled.as_tuple() == (10, 10, 20, 20)

    clipped = BoundingBox(-5, -5, 20, 20).clip_to_image((10, 10))
    assert clipped.as_tuple() == (0, 0, 10, 10)

    assert bb.contains_point(5, 5)
    assert bb.contains_point(15, 15)
    assert not bb.contains_point(16, 16)


def test_intersection_union_iou():
    a = BoundingBox(0, 0, 10, 10)
    b = BoundingBox(5, 5, 10, 10)

    inter = a.intersection(b)
    assert inter is not None
    assert inter.as_tuple() == (5, 5, 5, 5)

    uni = a.union(b)
    assert uni.as_tuple() == (0, 0, 15, 15)

    # IoU = 25 / (100 + 100 - 25) = 25/175
    assert a.iou(b) == pytest.approx(25 / 175)


def test_intersects_and_disjoint_iou_zero():
    a = BoundingBox(0, 0, 10, 10)
    b = BoundingBox(20, 20, 5, 5)
    assert not a.intersects(b)
    assert a.intersection(b) is None
    assert a.iou(b) == 0.0


def test_corners_and_from_corners():
    bb = BoundingBox(10, 20, 30, 40)
    corners = bb.to_corners()
    assert corners == [(10, 20), (40, 20), (40, 60), (10, 60)]

    bb2 = BoundingBox.from_corners(corners)
    assert bb2.as_tuple() == (10, 20, 30, 40)


def test_from_corners_too_few_points():
    with pytest.raises(ValueError):
        BoundingBox.from_corners([(0.0, 0.0)])


@pytest.mark.parametrize("shape", ["Nx2", "Nx1x2"])
def test_numpy_helpers(shape):
    missing_libs = check_libs(["numpy"])
    if missing_libs:
        pytest.skip(f"Required libraries not installed: {', '.join(missing_libs)}. Skipping test.")

    import numpy as np

    bb = BoundingBox(1, 2, 3, 4)
    arr = bb.to_corners_np(dtype="float32", shape=shape)
    if shape == "Nx2":
        assert arr.shape == (4, 2)
    else:
        assert arr.shape == (4, 1, 2)

    # Round-trip from corners
    if shape == "Nx1x2":
        flat = arr.reshape((-1, 2))
    else:
        flat = arr
    bb2 = BoundingBox.from_corners_np(flat)
    assert bb2.as_tuple() == (1.0, 2.0, 3.0, 4.0)

    # Also test from (N,1,2)
    bb3 = BoundingBox.from_corners_np(arr)
    assert bb3.as_tuple() == (1.0, 2.0, 3.0, 4.0)

    # Invalid shape option
    with pytest.raises(ValueError):
        bb.to_corners_np(shape="invalid")

    # Invalid corners array shape
    with pytest.raises(ValueError):
        BoundingBox.from_corners_np(np.zeros((4, 3), dtype=float))


def test_roi_slices():
    bb = BoundingBox(10.2, 20.8, 30.4, 40.7)
    rows, cols = bb.to_roi_slices()
    assert rows.start == 21 and rows.stop == 62
    assert cols.start == 10 and cols.stop == 41


def test_draw_on_pil_outline_and_fill_changes_pixels():
    img = Image.new("RGB", (100, 80), color=(255, 255, 255))
    bb = BoundingBox(10, 10, 30, 20)

    # Draw with fill to ensure interior pixels change
    img2 = bb.draw_on_pil(img, color=(255, 0, 0), width=2, fill=(0, 255, 0, 255), label="lbl")
    assert isinstance(img2, Image.Image)

    # Sample an interior pixel
    px = img2.getpixel((15, 15))
    assert px != (255, 255, 255)


def test_draw_on_pil_label_fallbacks(monkeypatch):
    img = Image.new("RGB", (100, 80), color=(255, 255, 255))
    bb = BoundingBox(5, 5, 10, 10)

    # Force ImageFont.load_default to raise to cover except path
    monkeypatch.setattr("PIL.ImageFont.load_default", lambda: (_ for _ in ()).throw(Exception("err")))
    # Remove textbbox attribute to use textsize fallback
    import PIL.ImageDraw as ID

    if hasattr(ID.ImageDraw, "textbbox"):
        monkeypatch.delattr(ID.ImageDraw, "textbbox", raising=False)

    img2 = bb.draw_on_pil(img, label="x")
    assert isinstance(img2, Image.Image)


def test_draw_on_pil_label_font_metrics_branches(monkeypatch):
    img = Image.new("RGB", (100, 80), color=(255, 255, 255))
    bb = BoundingBox(5, 5, 10, 10)

    # Ensure draw.textbbox is not available to trigger fallback branch
    import PIL.ImageDraw as ID

    if hasattr(ID.ImageDraw, "textbbox"):
        monkeypatch.delattr(ID.ImageDraw, "textbbox", raising=False)

    # Patch ImageDraw.ImageDraw.text to no-op to avoid PIL font requirements
    monkeypatch.setattr(ID.ImageDraw, "text", lambda self, xy, text, fill=None, font=None: None, raising=False)

    # Stub font with getbbox
    class FontBBox:
        def getbbox(self, text):
            return (0, 0, 7 * len(text), 11)

    img2 = bb.draw_on_pil(img.copy(), label="ab", font=FontBBox())
    assert isinstance(img2, Image.Image)

    # Stub font with getsize only
    class FontSize:
        def getsize(self, text):
            return (8 * len(text), 12)

    img3 = bb.draw_on_pil(img.copy(), label="cd", font=FontSize())
    assert isinstance(img3, Image.Image)


def test_draw_on_pil_label_font_default_dims(monkeypatch):
    # Trigger branch where font is provided but has neither getbbox nor getsize (line 129)
    img = Image.new("RGB", (100, 80), color=(255, 255, 255))
    bb = BoundingBox(5, 5, 10, 10)

    import PIL.ImageDraw as ID

    if hasattr(ID.ImageDraw, "textbbox"):
        monkeypatch.delattr(ID.ImageDraw, "textbbox", raising=False)

    # Patch text to no-op
    monkeypatch.setattr(ID.ImageDraw, "text", lambda self, xy, text, fill=None, font=None: None, raising=False)

    class DummyFont:
        pass

    img4 = bb.draw_on_pil(img.copy(), label="efg", font=DummyFont())
    assert isinstance(img4, Image.Image)


def test_to_corners_np_raises_without_numpy(monkeypatch):
    import mindtrace.core.types.bounding_box as bbmod

    monkeypatch.setattr(bbmod, "_HAS_NUMPY", False)
    # numpy not required to construct object; method should raise ImportError
    with pytest.raises(ImportError):
        BoundingBox(0, 0, 1, 1).to_corners_np()


def test_from_corners_np_raises_without_numpy(monkeypatch):
    import mindtrace.core.types.bounding_box as bbmod

    monkeypatch.setattr(bbmod, "_HAS_NUMPY", False)
    with pytest.raises(ImportError):
        BoundingBox.from_corners_np([[0.0, 0.0], [1.0, 0.0]])


def test_to_int():
    bb = BoundingBox(1.9, 2.1, 3.6, 4.4)
    bb2 = bb.to_int()
    assert bb2.as_tuple() == (2, 2, 4, 4)

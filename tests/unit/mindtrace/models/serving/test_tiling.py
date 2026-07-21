"""Unit tests for tiled inference (mindtrace.models.serving.tiling).

CPU-only and torch-free: exercises the tile grid geometry and the pure-numpy
cross-tile merge logic with a synthetic "detector" that finds a painted marker.
"""

from __future__ import annotations

import numpy as np
import pytest

from mindtrace.models.serving.tiling import TileDetection, TiledInference

TILE = (1024, 1024)
OVERLAP = 0.15


def _marker_detector(score: float = 0.9, label: int | str = 1):
    """Fake predict_fn: reports the bounding box of nonzero pixels in a tile."""

    def predict(tile: np.ndarray) -> list[dict]:
        ys, xs = np.nonzero(tile[:, :, 0])
        if xs.size == 0:
            return []
        box = (float(xs.min()), float(ys.min()), float(xs.max() + 1), float(ys.max() + 1))
        return [{"box": box, "score": score, "label": label}]

    return predict


def test_tiles_cover_large_frame_with_overlap_and_no_out_of_bounds():
    height, width = 1900, 2500
    tiler = TiledInference(lambda t: [], tile=TILE, overlap=OVERLAP)
    boxes = tiler.tiles((height, width))

    assert len(boxes) > 1
    coverage = np.zeros((height, width), dtype=bool)
    for x0, y0, x1, y1 in boxes:
        # Never exceeds the image, never degenerate: full-sized tiles only.
        assert 0 <= x0 < x1 <= width
        assert 0 <= y0 < y1 <= height
        assert (x1 - x0, y1 - y0) == (TILE[1], TILE[0])
        coverage[y0:y1, x0:x1] = True
    assert coverage.all(), "tile grid must cover every pixel of the frame"

    # Consecutive tiles in each axis share at least the requested overlap.
    min_overlap_px = int(round(TILE[0] * OVERLAP))
    x_starts = sorted({b[0] for b in boxes})
    y_starts = sorted({b[1] for b in boxes})
    for starts, tile_dim in ((x_starts, TILE[1]), (y_starts, TILE[0])):
        for prev, nxt in zip(starts, starts[1:]):
            assert prev + tile_dim - nxt >= min_overlap_px


def test_small_image_yields_single_tile_and_single_predict_call():
    calls: list[tuple[int, ...]] = []

    def predict(tile: np.ndarray) -> list[dict]:
        calls.append(tile.shape)
        return [{"box": (10.0, 20.0, 30.0, 40.0), "score": 0.8, "label": "scratch"}]

    tiler = TiledInference(predict, tile=TILE, overlap=OVERLAP)
    image = np.zeros((500, 400, 3), dtype=np.uint8)

    assert tiler.tiles(image.shape[:2]) == [(0, 0, 400, 500)]
    results = tiler.predict(image)

    assert calls == [(500, 400, 3)], "small image must be predicted in one call, unpadded"
    assert len(results) == 1
    assert isinstance(results[0], TileDetection)
    assert results[0].box == (10.0, 20.0, 30.0, 40.0)
    assert results[0].label == "scratch"


def test_object_seen_by_two_overlapping_tiles_merges_to_one_frame_coord_box():
    # Frame (H=1500, W=2000); x starts are [0, 870, 976], y starts [0, 476].
    # A marker at x:880-940, y:300-360 is fully inside tiles (0,0) and (870,0)
    # and entirely invisible to every other tile.
    image = np.zeros((1500, 2000, 3), dtype=np.uint8)
    image[300:360, 880:940, :] = 255

    tiler = TiledInference(_marker_detector(), tile=TILE, overlap=OVERLAP, merge="nms")
    results = tiler.predict(image)

    assert len(results) == 1, "the same physical object seen twice must NMS-merge to one box"
    assert results[0].box == (880.0, 300.0, 940.0, 360.0)
    assert results[0].score == pytest.approx(0.9)


def test_merge_none_returns_per_tile_duplicates():
    image = np.zeros((1500, 2000, 3), dtype=np.uint8)
    image[300:360, 880:940, :] = 255

    tiler = TiledInference(_marker_detector(), tile=TILE, overlap=OVERLAP, merge="none")
    results = tiler.predict(image)

    assert len(results) == 2
    assert all(r.box == (880.0, 300.0, 940.0, 360.0) for r in results)


def test_class_aware_nms_keeps_overlapping_boxes_of_different_labels():
    def predict(tile: np.ndarray) -> list[dict]:
        return [
            {"box": (100.0, 100.0, 200.0, 200.0), "score": 0.95, "label": "dent"},
            {"box": (105.0, 105.0, 205.0, 205.0), "score": 0.90, "label": "scratch"},
            {"box": (110.0, 110.0, 210.0, 210.0), "score": 0.60, "label": "dent"},
        ]

    tiler = TiledInference(predict, tile=TILE, overlap=OVERLAP, merge="nms", iou_threshold=0.5)
    results = tiler.predict(np.zeros((512, 512, 3), dtype=np.uint8))

    # High-IoU same-label pair collapses; the different-label box survives.
    assert len(results) == 2
    assert {r.label for r in results} == {"dent", "scratch"}
    dent = next(r for r in results if r.label == "dent")
    assert dent.score == pytest.approx(0.95)


def test_score_threshold_filters_low_confidence_detections():
    def predict(tile: np.ndarray) -> list[dict]:
        return [
            {"box": (0.0, 0.0, 10.0, 10.0), "score": 0.9, "label": 0},
            {"box": (50.0, 50.0, 60.0, 60.0), "score": 0.1, "label": 0},
        ]

    tiler = TiledInference(predict, tile=TILE, overlap=OVERLAP, score_threshold=0.5)
    results = tiler.predict(np.zeros((256, 256, 3), dtype=np.uint8))

    assert len(results) == 1
    assert results[0].score == pytest.approx(0.9)


def test_invalid_arguments_raise():
    with pytest.raises(ValueError):
        TiledInference(lambda t: [], overlap=1.0)
    with pytest.raises(ValueError):
        TiledInference(lambda t: [], merge="wbf")
    with pytest.raises(ValueError):
        TiledInference(lambda t: [], tile=(0, 1024))

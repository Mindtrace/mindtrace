"""Unit tests for AutoSegmenter.optimize_for_edge.

Tests cover:
- optimize_for_edge returns an AutoSegmenter wired to the edge checkpoints
- The detector recipe is recorded as edge_detector_recipe (None by default)
- No models are loaded and no export runs during construction
- kwargs pass through to the constructor
"""

from __future__ import annotations

from mindtrace.models.auto_segmenter import AutoSegmenter
from mindtrace.models.optimization.recipes import Export, OptimizationRecipe, Quantize


def test_optimize_for_edge_defaults():
    seg = AutoSegmenter.optimize_for_edge(live_service=False)

    assert isinstance(seg, AutoSegmenter)
    assert seg.yolo_model_name == "yolov10m.pt"
    assert seg.sam_model_name == "mobile_sam.pt"
    assert seg.edge_detector_recipe is None
    assert seg._yolo is None
    assert seg._sam is None
    assert seg.is_loaded is False


def test_optimize_for_edge_records_recipe_and_overrides():
    recipe = OptimizationRecipe(name="detector-int8", steps=[Export(), Quantize(mode="dynamic")])

    seg = AutoSegmenter.optimize_for_edge(
        detector_recipe=recipe,
        detector_model="yolov10s.pt",
        segmenter="sam2.1_t.pt",
        live_service=False,
    )

    assert seg.yolo_model_name == "yolov10s.pt"
    assert seg.sam_model_name == "sam2.1_t.pt"
    assert seg.edge_detector_recipe is recipe
    assert seg.edge_detector_recipe.name == "detector-int8"


def test_optimize_for_edge_does_not_load_models():
    seg = AutoSegmenter.optimize_for_edge(live_service=False)

    # Construction is configuration-only: no model objects, no export artifacts.
    assert seg._yolo is None
    assert seg._sam is None

from __future__ import annotations

import base64

import cv2
import numpy as np
import pytest

from mindtrace.models.auto_segmenter import AutoSegmenter, AutoSegmenterInput


class _ArrayWrap:
    def __init__(self, arr):
        self._arr = np.array(arr)

    def cpu(self):
        return self

    def numpy(self):
        return self._arr


class _FakeBoxes:
    def __init__(self, xyxy, conf, cls):
        self.xyxy = _ArrayWrap(xyxy)
        self.conf = _ArrayWrap(conf)
        self.cls = _ArrayWrap(cls)

    def __len__(self):
        return len(self.xyxy.numpy())


class _FakeYOLOResult:
    def __init__(self, boxes, names):
        self.boxes = boxes
        self.names = names


class _FakeSAMMasks:
    def __init__(self, data):
        self.data = _ArrayWrap(data)


class _FakeSAMResult:
    def __init__(self, masks):
        self.masks = masks


def _encode_test_image() -> str:
    img = np.zeros((8, 8, 3), dtype=np.uint8)
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return base64.b64encode(buf.tobytes()).decode("utf-8")


def test_auto_segmenter_on_load_and_unload(monkeypatch):
    created = {}

    def fake_yolo(name):
        created["yolo"] = name
        return object()

    def fake_sam(name):
        created["sam"] = name
        return object()

    monkeypatch.setattr("mindtrace.models.auto_segmenter.YOLO", fake_yolo)
    monkeypatch.setattr("mindtrace.models.auto_segmenter.SAM", fake_sam)

    seg = AutoSegmenter.__new__(AutoSegmenter)
    seg.yolo_model_name = "yolov10m.pt"
    seg.sam_model_name = "sam2.1_s.pt"
    seg._yolo = None
    seg._sam = None

    seg.on_load(payload=None)
    assert created["yolo"] == "yolov10m.pt"
    assert created["sam"] == "sam2.1_s.pt"

    seg.on_unload(payload=None)
    assert seg._yolo is None
    assert seg._sam is None


def test_auto_segmenter_decode_and_encode_helpers():
    b64 = _encode_test_image()
    arr = AutoSegmenter._decode_image(b64)
    assert arr.shape[:2] == (8, 8)

    mask = np.zeros((4, 4), dtype=np.uint8)
    mask[1:3, 1:3] = 1
    mask_b64 = AutoSegmenter._mask_to_base64_png(mask)
    assert isinstance(mask_b64, str)
    assert len(mask_b64) > 0


def test_auto_segmenter_decode_invalid_base64_raises():
    with pytest.raises(ValueError):
        AutoSegmenter._decode_image("not-base64!!")


def test_auto_segmenter_requires_loaded_and_models():
    seg = AutoSegmenter.__new__(AutoSegmenter)
    seg._loaded = False
    seg._yolo = None
    seg._sam = None

    with pytest.raises(RuntimeError, match="not loaded"):
        seg.auto_segment(AutoSegmenterInput(image_base64=_encode_test_image()))

    seg._loaded = True
    with pytest.raises(RuntimeError, match="models are not available"):
        seg.auto_segment(AutoSegmenterInput(image_base64=_encode_test_image()))


def test_auto_segmenter_returns_boxes_and_masks():
    seg = AutoSegmenter.__new__(AutoSegmenter)
    seg._loaded = True

    fake_boxes = _FakeBoxes(
        xyxy=[[1, 2, 6, 7], [0, 0, 3, 3]],
        conf=[0.9, 0.7],
        cls=[0, 1],
    )
    seg._yolo = lambda image, conf, iou, verbose: [_FakeYOLOResult(fake_boxes, {0: "person", 1: "dog"})]
    seg._sam = lambda image, bboxes, verbose: [
        _FakeSAMResult(_FakeSAMMasks(np.array([np.ones((8, 8)), np.eye(8)])))
    ]

    out = seg.auto_segment(AutoSegmenterInput(image_base64=_encode_test_image(), conf=0.2, iou=0.7))
    assert len(out.bboxes) == 2
    assert out.bboxes[0].class_name == "person"
    assert len(out.masks) == 2
    assert out.masks[0].bbox_index == 0


def test_auto_segmenter_returns_empty_masks_when_no_boxes():
    seg = AutoSegmenter.__new__(AutoSegmenter)
    seg._loaded = True
    seg._yolo = lambda image, conf, iou, verbose: [_FakeYOLOResult(_FakeBoxes([], [], []), {0: "person"})]
    seg._sam = lambda image, bboxes, verbose: []

    out = seg.auto_segment(AutoSegmenterInput(image_base64=_encode_test_image()))
    assert out.bboxes == []
    assert out.masks == []

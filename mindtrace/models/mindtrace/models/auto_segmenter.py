"""Auto-segmentation Brain built from Ultralytics YOLO + SAM.

This Brain runs object detection first, then uses detection boxes as prompts for
SAM segmentation.
"""

from __future__ import annotations

import base64
import binascii
from typing import Any

import cv2
import numpy as np
from pydantic import BaseModel, Field

from mindtrace.core import TaskSchema
from mindtrace.models.pipeline import BrainLoadInput, BrainUnloadInput, Pipeline

try:
    from ultralytics import SAM, YOLO
except Exception as e:  # pragma: no cover - import guard for optional runtime deps
    SAM = None
    YOLO = None
    _ULTRALYTICS_IMPORT_ERROR = e
else:
    _ULTRALYTICS_IMPORT_ERROR = None


class AutoSegmenterInput(BaseModel):
    """Input payload for auto-segmentation."""

    image_base64: str = Field(
        description=(
            "Input image as base64 string. May be raw base64 bytes or a data URL (e.g. data:image/png;base64,...)."
        )
    )
    conf: float = Field(default=0.25, ge=0.0, le=1.0, description="YOLO confidence threshold.")
    iou: float = Field(default=0.7, ge=0.0, le=1.0, description="YOLO IoU threshold.")


class BoundingBoxPrediction(BaseModel):
    """Detected bounding box with class/confidence metadata."""

    x1: float
    y1: float
    x2: float
    y2: float
    confidence: float
    class_id: int
    class_name: str


class SegmentationMaskPrediction(BaseModel):
    """Segmentation mask associated with a bounding box prompt."""

    bbox_index: int
    mask_base64_png: str


class AutoSegmenterOutput(BaseModel):
    """Output payload for auto-segmentation."""

    bboxes: list[BoundingBoxPrediction]
    masks: list[SegmentationMaskPrediction]


AutoSegmenterTaskSchema = TaskSchema(
    name="auto_segment",
    input_schema=AutoSegmenterInput,
    output_schema=AutoSegmenterOutput,
)


class AutoSegmenter(Pipeline):
    """Brain that combines YOLO detection with SAM segmentation.

    Defaults:
    - YOLO model: yolov10m.pt
    - SAM model: sam2.1_s.pt
    """

    def __init__(
        self,
        *args,
        yolo_model: str = "yolov10m.pt",
        sam_model: str = "sam2.1_s.pt",
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.yolo_model_name = yolo_model
        self.sam_model_name = sam_model
        self._yolo: Any | None = None
        self._sam: Any | None = None

        self.add_endpoint(path="/auto_segment", func=self.auto_segment, schema=AutoSegmenterTaskSchema)

    def on_load(self, payload: BrainLoadInput) -> None:
        """Load YOLO and SAM models."""
        if _ULTRALYTICS_IMPORT_ERROR is not None:
            raise RuntimeError("Ultralytics import failed; cannot load AutoSegmenter.") from _ULTRALYTICS_IMPORT_ERROR

        if self._yolo is None:
            self._yolo = YOLO(self.yolo_model_name)
        if self._sam is None:
            self._sam = SAM(self.sam_model_name)

    def on_unload(self, payload: BrainUnloadInput) -> None:
        """Unload YOLO and SAM models."""
        self._yolo = None
        self._sam = None

    def auto_segment(self, payload: AutoSegmenterInput) -> AutoSegmenterOutput:
        """Detect objects with YOLO and segment each box with SAM."""
        if not self.is_loaded:
            raise RuntimeError("AutoSegmenter is not loaded. Call /load first.")
        if self._yolo is None or self._sam is None:
            raise RuntimeError("AutoSegmenter models are not available.")

        image = self._decode_image(payload.image_base64)

        yolo_results = self._yolo(image, conf=payload.conf, iou=payload.iou, verbose=False)
        yolo_result = yolo_results[0]

        boxes: list[BoundingBoxPrediction] = []
        prompt_boxes_xyxy: list[list[float]] = []

        if yolo_result.boxes is not None and len(yolo_result.boxes) > 0:
            xyxy = yolo_result.boxes.xyxy.cpu().numpy()
            confs = yolo_result.boxes.conf.cpu().numpy()
            clss = yolo_result.boxes.cls.cpu().numpy()
            names = yolo_result.names

            for i in range(len(xyxy)):
                x1, y1, x2, y2 = xyxy[i].tolist()
                class_id = int(clss[i])
                class_name = str(names.get(class_id, str(class_id)))
                boxes.append(
                    BoundingBoxPrediction(
                        x1=float(x1),
                        y1=float(y1),
                        x2=float(x2),
                        y2=float(y2),
                        confidence=float(confs[i]),
                        class_id=class_id,
                        class_name=class_name,
                    )
                )
                prompt_boxes_xyxy.append([float(x1), float(y1), float(x2), float(y2)])

        if not prompt_boxes_xyxy:
            return AutoSegmenterOutput(bboxes=boxes, masks=[])

        sam_results = self._sam(image, bboxes=prompt_boxes_xyxy, verbose=False)
        sam_result = sam_results[0]

        masks: list[SegmentationMaskPrediction] = []
        if sam_result.masks is not None and sam_result.masks.data is not None:
            mask_tensor = sam_result.masks.data
            mask_np = mask_tensor.cpu().numpy().astype(np.uint8)
            for i, mask in enumerate(mask_np):
                masks.append(
                    SegmentationMaskPrediction(
                        bbox_index=i,
                        mask_base64_png=self._mask_to_base64_png(mask),
                    )
                )

        return AutoSegmenterOutput(bboxes=boxes, masks=masks)

    @staticmethod
    def _decode_image(image_base64: str) -> np.ndarray:
        """Decode base64 image (raw or data URL) into an OpenCV BGR ndarray."""
        raw = image_base64.strip()
        if "," in raw and raw.startswith("data:"):
            raw = raw.split(",", 1)[1]

        try:
            image_bytes = base64.b64decode(raw, validate=True)
        except binascii.Error as e:
            raise ValueError("Invalid base64 image payload.") from e

        np_bytes = np.frombuffer(image_bytes, dtype=np.uint8)
        image = cv2.imdecode(np_bytes, cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("Failed to decode image bytes.")
        return image

    @staticmethod
    def _mask_to_base64_png(mask: np.ndarray) -> str:
        """Encode a binary mask ndarray as base64 PNG."""
        mask_u8 = (mask > 0).astype(np.uint8) * 255
        ok, encoded = cv2.imencode(".png", mask_u8)
        if not ok:
            raise RuntimeError("Failed to encode segmentation mask.")
        return base64.b64encode(encoded.tobytes()).decode("utf-8")

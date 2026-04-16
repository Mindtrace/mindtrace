"""Typed vault-facing annotation models (discriminated by :attr:`kind`).

These mirror :data:`~mindtrace.datalake.types.AnnotationKind` and serialize to the
``dict`` shape accepted by :meth:`~mindtrace.datalake.AsyncDatalake.add_annotation_records`.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field

from mindtrace.datalake.types import AnnotationKind, AnnotationRecord, AnnotationSource, StorageRef


class _AnnotationCommon(BaseModel):
    """Shared fields for persisted annotation rows (excluding ``subject``, set by the vault)."""

    label: str
    label_id: int | None = None
    score: float | None = None
    source: AnnotationSource
    attributes: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def _row_payload(self, *, kind: str, geometry: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {
            "kind": kind,
            "label": self.label,
            "source": self.source.model_dump(),
            "geometry": geometry,
            "attributes": self.attributes,
            "metadata": self.metadata,
        }
        if self.label_id is not None:
            out["label_id"] = self.label_id
        if self.score is not None:
            out["score"] = self.score
        return out


class ClassificationAnnotation(_AnnotationCommon):
    kind: Literal["classification"] = "classification"

    def to_payload(self) -> dict[str, Any]:
        return self._row_payload(kind="classification", geometry={})

    @classmethod
    def from_record(cls, record: AnnotationRecord) -> ClassificationAnnotation:
        return cls.model_validate(
            {
                "kind": "classification",
                "label": record.label,
                "label_id": record.label_id,
                "score": record.score,
                "source": record.source.model_dump(),
                "attributes": record.attributes,
                "metadata": record.metadata,
            }
        )


class RegressionAnnotation(_AnnotationCommon):
    kind: Literal["regression"] = "regression"
    value: float

    def to_payload(self) -> dict[str, Any]:
        return self._row_payload(kind="regression", geometry={"value": self.value})

    @classmethod
    def from_record(cls, record: AnnotationRecord) -> RegressionAnnotation:
        g = record.geometry or {}
        return cls.model_validate(
            {
                "kind": "regression",
                "label": record.label,
                "label_id": record.label_id,
                "score": record.score,
                "source": record.source.model_dump(),
                "attributes": record.attributes,
                "metadata": record.metadata,
                "value": float(g.get("value", g.get("target", 0.0))),
            }
        )


class BboxAnnotation(_AnnotationCommon):
    kind: Literal["bbox"] = "bbox"
    x: float
    y: float
    width: float
    height: float

    def to_payload(self) -> dict[str, Any]:
        return self._row_payload(
            kind="bbox",
            geometry={"x": self.x, "y": self.y, "width": self.width, "height": self.height},
        )

    @classmethod
    def from_record(cls, record: AnnotationRecord) -> BboxAnnotation:
        g = record.geometry or {}
        return cls.model_validate(
            {
                "kind": "bbox",
                "label": record.label,
                "label_id": record.label_id,
                "score": record.score,
                "source": record.source.model_dump(),
                "attributes": record.attributes,
                "metadata": record.metadata,
                "x": g["x"],
                "y": g["y"],
                "width": g["width"],
                "height": g["height"],
            }
        )


class RotatedBboxAnnotation(_AnnotationCommon):
    kind: Literal["rotated_bbox"] = "rotated_bbox"
    cx: float
    cy: float
    width: float
    height: float
    angle: float = 0.0

    def to_payload(self) -> dict[str, Any]:
        return self._row_payload(
            kind="rotated_bbox",
            geometry={
                "cx": self.cx,
                "cy": self.cy,
                "width": self.width,
                "height": self.height,
                "angle": self.angle,
            },
        )

    @classmethod
    def from_record(cls, record: AnnotationRecord) -> RotatedBboxAnnotation:
        g = record.geometry or {}
        return cls.model_validate(
            {
                "kind": "rotated_bbox",
                "label": record.label,
                "label_id": record.label_id,
                "score": record.score,
                "source": record.source.model_dump(),
                "attributes": record.attributes,
                "metadata": record.metadata,
                "cx": g["cx"],
                "cy": g["cy"],
                "width": g["width"],
                "height": g["height"],
                "angle": float(g.get("angle", 0.0)),
            }
        )


class PolygonAnnotation(_AnnotationCommon):
    kind: Literal["polygon"] = "polygon"
    vertices: list[list[float]]

    def to_payload(self) -> dict[str, Any]:
        return self._row_payload(kind="polygon", geometry={"vertices": self.vertices})

    @classmethod
    def from_record(cls, record: AnnotationRecord) -> PolygonAnnotation:
        g = record.geometry or {}
        verts = g.get("vertices") or g.get("points") or []
        return cls.model_validate(
            {
                "kind": "polygon",
                "label": record.label,
                "label_id": record.label_id,
                "score": record.score,
                "source": record.source.model_dump(),
                "attributes": record.attributes,
                "metadata": record.metadata,
                "vertices": verts,
            }
        )


class PolylineAnnotation(_AnnotationCommon):
    kind: Literal["polyline"] = "polyline"
    points: list[list[float]]

    def to_payload(self) -> dict[str, Any]:
        return self._row_payload(kind="polyline", geometry={"points": self.points})

    @classmethod
    def from_record(cls, record: AnnotationRecord) -> PolylineAnnotation:
        g = record.geometry or {}
        pts = g.get("points") or g.get("vertices") or []
        return cls.model_validate(
            {
                "kind": "polyline",
                "label": record.label,
                "label_id": record.label_id,
                "score": record.score,
                "source": record.source.model_dump(),
                "attributes": record.attributes,
                "metadata": record.metadata,
                "points": pts,
            }
        )


class EllipseAnnotation(_AnnotationCommon):
    kind: Literal["ellipse"] = "ellipse"
    cx: float
    cy: float
    rx: float
    ry: float
    rotation: float = 0.0

    def to_payload(self) -> dict[str, Any]:
        return self._row_payload(
            kind="ellipse",
            geometry={
                "cx": self.cx,
                "cy": self.cy,
                "rx": self.rx,
                "ry": self.ry,
                "rotation": self.rotation,
            },
        )

    @classmethod
    def from_record(cls, record: AnnotationRecord) -> EllipseAnnotation:
        g = record.geometry or {}
        return cls.model_validate(
            {
                "kind": "ellipse",
                "label": record.label,
                "label_id": record.label_id,
                "score": record.score,
                "source": record.source.model_dump(),
                "attributes": record.attributes,
                "metadata": record.metadata,
                "cx": g["cx"],
                "cy": g["cy"],
                "rx": g["rx"],
                "ry": g["ry"],
                "rotation": float(g.get("rotation", 0.0)),
            }
        )


class KeypointAnnotation(_AnnotationCommon):
    kind: Literal["keypoint"] = "keypoint"
    keypoints: list[dict[str, Any]]

    def to_payload(self) -> dict[str, Any]:
        return self._row_payload(kind="keypoint", geometry={"keypoints": self.keypoints})

    @classmethod
    def from_record(cls, record: AnnotationRecord) -> KeypointAnnotation:
        g = record.geometry or {}
        kps = g.get("keypoints") or g.get("points") or []
        return cls.model_validate(
            {
                "kind": "keypoint",
                "label": record.label,
                "label_id": record.label_id,
                "score": record.score,
                "source": record.source.model_dump(),
                "attributes": record.attributes,
                "metadata": record.metadata,
                "keypoints": kps,
            }
        )


class MaskAnnotation(_AnnotationCommon):
    kind: Literal["mask"] = "mask"
    mask_asset_id: str | None = None
    storage_ref: StorageRef | None = None
    encoding: dict[str, Any] | None = None

    def to_payload(self) -> dict[str, Any]:
        geom: dict[str, Any] = {}
        if self.mask_asset_id is not None:
            geom["mask_asset_id"] = self.mask_asset_id
        if self.storage_ref is not None:
            geom["storage_ref"] = self.storage_ref.model_dump()
        if self.encoding is not None:
            geom["encoding"] = self.encoding
        return self._row_payload(kind="mask", geometry=geom)

    @classmethod
    def from_record(cls, record: AnnotationRecord) -> MaskAnnotation:
        g = record.geometry or {}
        sr = g.get("storage_ref")
        if sr is not None and not isinstance(sr, StorageRef):
            sr = StorageRef(**sr) if isinstance(sr, dict) else sr
        return cls.model_validate(
            {
                "kind": "mask",
                "label": record.label,
                "label_id": record.label_id,
                "score": record.score,
                "source": record.source.model_dump(),
                "attributes": record.attributes,
                "metadata": record.metadata,
                "mask_asset_id": g.get("mask_asset_id"),
                "storage_ref": sr,
                "encoding": g.get("encoding"),
            }
        )


class InstanceMaskAnnotation(_AnnotationCommon):
    kind: Literal["instance_mask"] = "instance_mask"
    mask_asset_id: str | None = None
    storage_ref: StorageRef | None = None
    encoding: dict[str, Any] | None = None
    instance_id: int | str | None = None

    def to_payload(self) -> dict[str, Any]:
        geom: dict[str, Any] = {}
        if self.mask_asset_id is not None:
            geom["mask_asset_id"] = self.mask_asset_id
        if self.storage_ref is not None:
            geom["storage_ref"] = self.storage_ref.model_dump()
        if self.encoding is not None:
            geom["encoding"] = self.encoding
        if self.instance_id is not None:
            geom["instance_id"] = self.instance_id
        return self._row_payload(kind="instance_mask", geometry=geom)

    @classmethod
    def from_record(cls, record: AnnotationRecord) -> InstanceMaskAnnotation:
        g = record.geometry or {}
        sr = g.get("storage_ref")
        if sr is not None and not isinstance(sr, StorageRef):
            sr = StorageRef(**sr) if isinstance(sr, dict) else sr
        return cls.model_validate(
            {
                "kind": "instance_mask",
                "label": record.label,
                "label_id": record.label_id,
                "score": record.score,
                "source": record.source.model_dump(),
                "attributes": record.attributes,
                "metadata": record.metadata,
                "mask_asset_id": g.get("mask_asset_id"),
                "storage_ref": sr,
                "encoding": g.get("encoding"),
                "instance_id": g.get("instance_id"),
            }
        )


class PointcloudSegmentationAnnotation(_AnnotationCommon):
    kind: Literal["pointcloud_segmentation"] = "pointcloud_segmentation"
    geometry: dict[str, Any] = Field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return self._row_payload(kind="pointcloud_segmentation", geometry=dict(self.geometry))

    @classmethod
    def from_record(cls, record: AnnotationRecord) -> PointcloudSegmentationAnnotation:
        return cls.model_validate(
            {
                "kind": "pointcloud_segmentation",
                "label": record.label,
                "label_id": record.label_id,
                "score": record.score,
                "source": record.source.model_dump(),
                "attributes": record.attributes,
                "metadata": record.metadata,
                "geometry": record.geometry or {},
            }
        )


AnnotationVariants = Union[
    ClassificationAnnotation,
    RegressionAnnotation,
    BboxAnnotation,
    RotatedBboxAnnotation,
    PolygonAnnotation,
    PolylineAnnotation,
    EllipseAnnotation,
    KeypointAnnotation,
    MaskAnnotation,
    InstanceMaskAnnotation,
    PointcloudSegmentationAnnotation,
]

Annotation = Annotated[AnnotationVariants, Field(discriminator="kind")]


def annotation_from_record(record: AnnotationRecord) -> AnnotationVariants:
    """Parse a persisted :class:`~mindtrace.datalake.types.AnnotationRecord` into a typed model."""
    kind: AnnotationKind = record.kind
    if kind == "classification":
        return ClassificationAnnotation.from_record(record)
    if kind == "regression":
        return RegressionAnnotation.from_record(record)
    if kind == "bbox":
        return BboxAnnotation.from_record(record)
    if kind == "rotated_bbox":
        return RotatedBboxAnnotation.from_record(record)
    if kind == "polygon":
        return PolygonAnnotation.from_record(record)
    if kind == "polyline":
        return PolylineAnnotation.from_record(record)
    if kind == "ellipse":
        return EllipseAnnotation.from_record(record)
    if kind == "keypoint":
        return KeypointAnnotation.from_record(record)
    if kind == "mask":
        return MaskAnnotation.from_record(record)
    if kind == "instance_mask":
        return InstanceMaskAnnotation.from_record(record)
    if kind == "pointcloud_segmentation":
        return PointcloudSegmentationAnnotation.from_record(record)
    raise ValueError(f"Unsupported annotation kind for typed vault model: {kind!r}")


__all__ = [
    "Annotation",
    "AnnotationVariants",
    "annotation_from_record",
    "BboxAnnotation",
    "ClassificationAnnotation",
    "EllipseAnnotation",
    "InstanceMaskAnnotation",
    "KeypointAnnotation",
    "MaskAnnotation",
    "PointcloudSegmentationAnnotation",
    "PolygonAnnotation",
    "PolylineAnnotation",
    "RegressionAnnotation",
    "RotatedBboxAnnotation",
]

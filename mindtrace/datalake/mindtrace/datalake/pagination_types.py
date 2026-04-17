from __future__ import annotations

from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, Field

from mindtrace.datalake.types import AnnotationRecord, AnnotationSet, Asset

PageItemT = TypeVar("PageItemT")

DEFAULT_PAGE_LIMIT = 100
MAX_PAGE_LIMIT = 500


class PageInfo(BaseModel):
    """Shared page metadata for cursor-based list and view responses."""

    limit: int = Field(default=DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT)
    next_cursor: str | None = None
    has_more: bool
    total_count: int | None = None


class CursorEnvelope(BaseModel):
    """Opaque cursor payload shape used internally before encoding for clients."""

    resource: str
    sort: str
    filter_fingerprint: str
    last_key: dict[str, Any] = Field(default_factory=dict)
    snapshot_token: str | None = None


class CursorPage(BaseModel, Generic[PageItemT]):
    """Generic page envelope shared across paginated datalake responses."""

    items: list[PageItemT] = Field(default_factory=list)
    page: PageInfo


class PageRequest(BaseModel):
    """Base request contract for cursor-based collection pagination."""

    limit: int = Field(default=DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT)
    cursor: str | None = None
    sort: str = "created_desc"
    include_total: bool = False


class StructuredFilter(BaseModel):
    """Structured filter contract for paginated query and dataset view APIs."""

    field: str
    op: Literal["eq", "ne", "gt", "gte", "lt", "lte", "in", "contains", "exists"]
    value: Any = None


class DatasetViewExpand(BaseModel):
    """Controls how much of the datum graph is expanded in each dataset view row."""

    assets: bool = True
    annotation_sets: bool = False
    annotation_records: bool = False


class DatasetViewRequest(PageRequest):
    """Cursor-based request contract for dataset view APIs."""

    sort: str = "manifest_order"
    filters: list[StructuredFilter] = Field(default_factory=list)
    expand: DatasetViewExpand = Field(default_factory=DatasetViewExpand)


class DatasetViewRow(BaseModel):
    """One row of a paginated dataset view."""

    datum_id: str
    split: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    assets: dict[str, Asset] | None = None
    annotation_sets: list[AnnotationSet] | None = None
    annotation_records: dict[str, list[AnnotationRecord]] | None = None


class DatasetViewInfo(BaseModel):
    """Descriptor for the dataset view represented by a paginated response."""

    dataset_name: str
    version: str
    sort: str = "manifest_order"


class DatasetViewPage(BaseModel):
    """Paginated dataset view response contract."""

    items: list[DatasetViewRow] = Field(default_factory=list)
    page: PageInfo
    view: DatasetViewInfo

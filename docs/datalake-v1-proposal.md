# Datalake v1 Proposal

## Summary

This proposal sketches a first canonical Datalake model for Mindtrace that preserves the strongest ideas from the initial design sketches while tightening the parts that are currently ambiguous.

The intended shape is:

- payloads live in Registry / Store-backed object storage
- structured metadata and annotations live in a database / ODM layer
- `Datum` is the unit of dataset membership
- `DatasetVersion` is immutable
- `DatasetBuilder` is mutable and used to derive new dataset versions
- Datalake exposes a service API for storage, assets, datasets, and annotations

This design is meant to support Chiron first, but should be framed as a reusable Mindtrace module rather than a Chiron-specific subsystem.

---

## Goals

- Define a canonical data model for Datalake in Mindtrace.
- Support remote payload storage across multiple backends via `Store` / `Registry`.
- Support structured metadata and annotation persistence in a database.
- Preserve immutable dataset-version semantics.
- Support query-generated dataset views.
- Support both Mindtrace-native datasets and HuggingFace dataset interoperability.
- Keep the v1 API small enough to implement without building the entire future platform at once.

## Non-goals

- Full enterprise data catalog in v1.
- Full lineage graph and lifecycle management in v1.
- Arbitrary Python-callable query execution over RPC.
- Fully automatic reference-counted garbage collection across all stored objects in v1.
- Replacing every existing application-level workflow with Datalake on day one.

---

## Strongest parts of the existing design

### 1. Split payload storage from metadata storage

This is the strongest architectural decision in the current sketches.

- Payloads such as images, masks, artifacts, and exports belong in Registry / Store-backed object storage.
- Structured metadata, manifests, and annotations belong in a database / ODM layer.

This enables:

- large-scale remote storage on NAS / MinIO / GCP
- lightweight queryability over metadata and labels
- app-independent asset reuse
- clean separation between storage concerns and annotation/query concerns

### 2. `Datum` as the unit of dataset membership

The idea that a dataset is composed of datums is strong and should be preserved.

A datum can point to one or more stored payloads while also carrying:

- structured metadata
- split membership
- links to annotation sets

This supports reusable assets, derived datasets, and query-generated views without forcing deep copies.

### 3. Immutable `Dataset` with mutable `DatasetBuilder`

This is a very good modeling choice.

- `Dataset` should represent an immutable view / version.
- `DatasetBuilder` should represent a mutable changeset used to construct a new dataset version.

This makes versioning more natural and prevents accidental mutation of registered datasets.

### 4. View semantics by default

Returning dataset views from the Datalake without copying payloads is the right default behavior.

This keeps registration and querying cheap, and aligns with the idea that datasets are reference-based compositions over stored datums and assets.

### 5. Query-generated datasets

Generating datasets from metadata / annotation filters is a powerful capability and should remain a first-class feature.

### 6. Mindtrace-native datasets plus HuggingFace interoperability

Supporting a native Mindtrace data model while providing conversion to / from HuggingFace datasets is a strong long-term direction.

---

## Weak or ambiguous parts of the current sketches

### 1. Canonical annotations are mixed with task/job output classes

The current sketches blur together:

- task-level result containers (`ImageDetectionAnnotation`, `SemanticSegmentationAnnotation`, etc.)
- atomic persisted annotation records (one bbox, one mask, one classification label)

For Datalake persistence and querying, the canonical model should be based on atomic annotation records, not nested job-output-shaped objects.

### 2. `Datum.metadata` and `Datum.annotations` are too loosely defined

`metadata` should be descriptive/filterable metadata.

`annotations` should be canonical structured annotation records or references to annotation sets.

If that boundary remains fuzzy, metadata risks becoming a catch-all JSON blob.

### 3. `Datum.data` is too unconstrained

The current idea of `data: dict[str, Archivable | str]` is flexible, but too vague as a canonical schema.

The model needs a more explicit representation of payload-bearing assets and their roles.

### 4. Reference counting is mentioned but not clearly modeled

The sketches suggest dataset deletion may decrement reference counts and garbage-collect payloads.

That may be desirable long-term, but it is not yet sufficiently specified to be a v1 contract.

### 5. `Dataset` is trying to be too many things at once

At the API/schema level, we should separate:

- dataset version record
- dataset view object / Python runtime wrapper
- archive/export forms

A Python class can still provide a nice user-facing abstraction, but the canonical service model should be more explicit.

### 6. Query API as arbitrary Python `Callable`

This is a nice SDK shorthand, but not a service contract.

The Datalake API should expose structured declarative filters, while Python helpers can compile lambdas / helper expressions into that representation later.

### 7. Version semantics need separation

The design currently risks conflating:

- dataset version
- payload object version
- annotation revision / snapshot version

These must remain distinct.

---

## Canonical v1 entities

The following entities preserve the spirit of the sketches while tightening the model.

### 1. `StorageRef`

A reference to a stored payload object.

```python
StorageRef:
    mount: str
    name: str
    version: str | None = "latest"
    qualified_key: str | None = None
```

Notes:

- `mount` maps naturally to a `Store` mount such as `temp`, `nas`, or `gcp`.
- `name` is the unqualified object key within that mount.
- `version` refers to the storage-layer version, not the dataset version.

### 2. `Asset`

A canonical record for a payload-bearing object.

```python
Asset:
    asset_id: str
    kind: Literal["image", "mask", "artifact", "embedding", "document", "other"]
    media_type: str
    storage_ref: StorageRef
    checksum: str | None = None
    size_bytes: int | None = None
    metadata: dict[str, Any] = {}
    created_at: datetime
    created_by: str | None = None
```

Notes:

- An asset is the catalog record for a payload in backing storage.
- This cleanly separates payload storage from dataset membership and annotation meaning.

### 3. `AnnotationSource`

Describes where an annotation came from.

```python
AnnotationSource:
    type: Literal["human", "machine", "derived"]
    name: str
    version: str | None = None
    metadata: dict[str, Any] = {}
```

Examples:

- `{"type": "human", "name": "review-ui"}`
- `{"type": "machine", "name": "yolo", "version": "1.2.0"}`
- `{"type": "derived", "name": "bbox-to-mask"}`

### 4. `AnnotationRecord`

One atomic annotation.

```python
AnnotationRecord:
    annotation_id: str
    datum_id: str
    annotation_set_id: str
    kind: Literal[
        "classification",
        "bbox",
        "rotated_bbox",
        "polygon",
        "polyline",
        "ellipse",
        "keypoint",
        "mask",
        "instance_mask",
    ]
    label: str
    label_id: int | None = None
    score: float | None = None
    source: AnnotationSource
    geometry: dict[str, Any]
    attributes: dict[str, Any] = {}
    created_at: datetime
    updated_at: datetime
```

Example geometry payloads:

```json
{ "type": "bbox", "x": 10, "y": 20, "width": 30, "height": 40 }
```

```json
{
  "type": "rotated_bbox",
  "cx": 10,
  "cy": 20,
  "width": 30,
  "height": 40,
  "angle_deg": 15
}
```

```json
{
  "type": "mask",
  "encoding": "rle_row_major_v1",
  "counts": [12, 4, 91],
  "size": [1080, 1920],
  "bbox": { "x": 10, "y": 20, "width": 30, "height": 40 }
}
```

Notes:

- Atomic records are easier to query, edit, and export.
- Job outputs should map into these records rather than become the canonical storage format.

### 5. `AnnotationSet`

A grouping and provenance boundary for annotation records.

```python
AnnotationSet:
    annotation_set_id: str
    dataset_version_id: str | None = None
    name: str
    purpose: Literal["ground_truth", "prediction", "review", "snapshot", "other"]
    source_type: Literal["human", "machine", "mixed"]
    status: Literal["draft", "active", "archived"]
    metadata: dict[str, Any] = {}
    created_at: datetime
    created_by: str | None = None
```

Notes:

- This allows multiple annotation layers over the same underlying datum.
- Useful distinctions include human truth vs machine predictions vs reviewed snapshots.

### 6. `Datum`

The unit of dataset membership.

```python
Datum:
    datum_id: str
    dataset_version_id: str
    split: Literal["train", "val", "test"] | None = None
    asset_refs: dict[str, str]  # role -> asset_id
    metadata: dict[str, Any] = {}
    annotation_set_ids: list[str] = []
    created_at: datetime
```

Notes:

- `asset_refs` can map roles like `image`, `thumbnail`, `aux_mask`, or `roi_crop` to asset IDs.
- Datums should link to annotation sets instead of embedding all annotation payloads directly.

### 7. `DatasetVersion`

An immutable dataset record.

```python
DatasetVersion:
    dataset_version_id: str
    dataset_name: str
    version: str
    description: str | None = None
    manifest: list[str]  # datum_ids
    source_dataset_version_id: str | None = None
    metadata: dict[str, Any] = {}
    created_at: datetime
    created_by: str | None = None
```

Notes:

- This preserves the immutable dataset concept from the sketches.
- A runtime `Dataset` object can wrap this record and provide a Pythonic interface.

### 8. `DatasetBuilder`

`DatasetBuilder` should remain part of the SDK / Python workflow surface rather than become a primary persisted schema.

It represents staged mutations used to produce a new `DatasetVersion`.

---

## Canonical semantic rule

The most important semantic rule for v1 should be:

> Dataset versions are immutable views over datum membership; assets and annotations are persisted separately and referenced by those views.

This preserves the best part of the original design while keeping the data model normalized and extensible.

---

## Proposed minimal v1 API

The API should be split into four slices:

- storage
- assets
- datasets
- annotations

### A. Storage / mounts API

#### `GET /api/v1/datalake/health`

Basic service health.

#### `GET /api/v1/datalake/mounts`

List configured mounts and default mount information.

Example response:

```json
{
  "default_mount": "nas",
  "mounts": [
    {
      "name": "temp",
      "read_only": false,
      "backend": "file:///tmp/mindtrace-store-abc123",
      "version_objects": false,
      "mutable": true
    },
    {
      "name": "nas",
      "read_only": false,
      "backend": "s3://minio/chiron",
      "version_objects": true,
      "mutable": true
    },
    {
      "name": "gcp",
      "read_only": false,
      "backend": "gs://my-bucket/chiron",
      "version_objects": true,
      "mutable": true
    }
  ]
}
```

#### `POST /api/v1/datalake/objects/put`

Persist a raw payload into the configured Store / Registry layer.

Example request:

```json
{
  "mount": "nas",
  "name": "project:p1:image:img1",
  "version": "latest",
  "content_base64": "...",
  "content_type": "image/jpeg",
  "metadata": {
    "filename": "foo.jpg",
    "project_id": "p1"
  },
  "on_conflict": "overwrite"
}
```

#### `POST /api/v1/datalake/objects/get`

Retrieve a raw payload.

#### `POST /api/v1/datalake/objects/head`

Inspect a storage object without returning the payload.

#### `POST /api/v1/datalake/objects/copy`

Copy an object between mounts.

This is especially important for NAS -> GCP promotion workflows.

### B. Assets API

#### `POST /api/v1/datalake/assets`

Register an asset record for a stored payload.

Example request:

```json
{
  "kind": "image",
  "media_type": "image/jpeg",
  "storage_ref": {
    "mount": "nas",
    "name": "project:p1:image:img1",
    "version": "latest"
  },
  "checksum": "sha256:...",
  "size_bytes": 12345,
  "metadata": {
    "filename": "foo.jpg",
    "project_id": "p1"
  }
}
```

#### `GET /api/v1/datalake/assets/{asset_id}`

Fetch asset metadata.

#### `GET /api/v1/datalake/assets`

List/filter assets by kind, project, metadata, or pagination.

#### `DELETE /api/v1/datalake/assets/{asset_id}`

Delete an asset record. Underlying payload deletion policy may remain conservative in v1.

### C. Datasets API

#### `POST /api/v1/datalake/datasets`

Create/register a new immutable dataset version.

This should accept:

- dataset name
- version
- manifest / datum membership
- optionally a builder-derived payload

#### `GET /api/v1/datalake/datasets`

List datasets.

#### `GET /api/v1/datalake/datasets/{dataset_name}/versions`

List versions for a dataset.

#### `GET /api/v1/datalake/datasets/{dataset_name}/versions/{version}`

Fetch dataset version metadata.

#### `POST /api/v1/datalake/datasets/{dataset_name}/versions/{version}/view`

Return a paginated dataset view descriptor.

#### `POST /api/v1/datalake/datasets/query`

Create a derived dataset view using structured filters.

Example request:

```json
{
  "dataset": "all",
  "split": "train",
  "filters": [
    { "field": "metadata.label", "op": "eq", "value": "undercut" },
    { "field": "metadata.severity", "op": "gt", "value": 3.0 }
  ]
}
```

This preserves the spirit of `from_query(...)` while replacing a Python `Callable` with a proper service contract.

### D. Datum API

#### `POST /api/v1/datalake/datums`

Create one or more datums.

#### `GET /api/v1/datalake/datums/{datum_id}`

Fetch datum metadata.

#### `GET /api/v1/datalake/datums`

Filter datums by dataset version, split, or metadata.

#### `PATCH /api/v1/datalake/datums/{datum_id}`

Update mutable datum metadata before finalization if allowed.

### E. Annotation API

#### `POST /api/v1/datalake/annotation-sets`

Create a new annotation set.

#### `GET /api/v1/datalake/annotation-sets/{annotation_set_id}`

Fetch annotation set metadata.

#### `GET /api/v1/datalake/annotation-sets`

List/filter annotation sets.

#### `POST /api/v1/datalake/annotations`

Create one or more annotation records.

Example request:

```json
{
  "annotation_set_id": "aset-1",
  "annotations": [
    {
      "datum_id": "datum-1",
      "kind": "bbox",
      "label": "crack",
      "score": 0.92,
      "source": {
        "type": "machine",
        "name": "yolo",
        "version": "1.0.0"
      },
      "geometry": {
        "type": "bbox",
        "x": 1,
        "y": 2,
        "width": 3,
        "height": 4
      },
      "attributes": {
        "severity": "high"
      }
    }
  ]
}
```

#### `GET /api/v1/datalake/annotations`

Filter annotation records by datum, set, kind, label, or source.

#### `PATCH /api/v1/datalake/annotations/{annotation_id}`

Update an annotation record.

#### `DELETE /api/v1/datalake/annotations/{annotation_id}`

Delete an annotation record.

---

## Chiron integration notes

This proposal is intended to support Chiron as an early client without making the Datalake model Chiron-specific.

In a Datalake-backed Chiron flow:

- image payloads would be stored through the storage / asset APIs
- image records in Chiron could point at canonical Datalake asset IDs
- label CRUD could move to the Datalake annotation APIs when desired
- dataset exports could be generated from canonical assets and annotation records
- NAS / GCP promotion could happen through storage copy endpoints

This allows Chiron to become a Datalake client rather than the long-term owner of the canonical annotation persistence model.

---

## Open questions

The following are intentionally left open for later design decisions:

1. **Reference counting and garbage collection**
   - Should v1 maintain explicit reference counts on assets?
   - Should this be derived rather than eagerly tracked?

2. **Taxonomy / ontology support**
   - Should class maps and label ontologies become first-class entities in v1 or later?

3. **Transaction semantics**
   - How tightly do we want to coordinate DB writes and Store writes?
   - Is eventual consistency acceptable in v1?

4. **Query language**
   - What structured filter language should be adopted for dataset and annotation queries?

5. **Runtime SDK surface**
   - How much of the Python ergonomic layer (`Dataset`, `DatasetBuilder`, HF interop helpers) should ship in the first implementation?

6. **Access control / multi-tenant concerns**
   - Should authorization remain outside the Datalake service for v1, or be partly absorbed later?

---

## Recommended v1 implementation stance

A practical first implementation should:

- preserve the Registry / Store + database split
- implement explicit canonical entities for assets, datums, dataset versions, annotation sets, and atomic annotation records
- keep the service API small and explicit
- avoid overpromising advanced lifecycle mechanics in the first cut

In short: build the Datalake as a canonical data layer with a narrow, clear contract, not as a one-off Chiron storage helper and not as a giant platform on day one.

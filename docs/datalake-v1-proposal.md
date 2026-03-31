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

This design is intended to be a reusable Mindtrace module rather than an application-specific subsystem.

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

## Review of the previous `mtrix` Datalake

The previous `mtrix` package included a `datalake` module that is useful to study because it solved a real set of problems well, but it also reveals why a new Datalake iteration is necessary.

### What the previous Datalake was

The `mtrix` Datalake was primarily a dataset lifecycle and synchronization system.

At a high level it combined:

- a thin top-level `Datalake` facade
- a `ServiceRegistry` for dependency wiring
- service classes for discovery, provisioning, synchronization, loading, and manifest handling
- manifest-driven dataset versioning
- local filesystem dataset layouts
- Hugging Face as a registry / discovery plane
- GCP as blob storage
- Arrow / Hugging Face dataset cache building for loading

In other words, the prior design was less a generalized canonical datalake and more a dataset packaging, synchronization, and loading framework.

### What it did

The previous Datalake supported a concrete end-to-end workflow:

1. **Create a dataset locally** from a source directory.
2. **Validate it** by attempting to build cache through a Hugging Face `GeneratorBasedBuilder`.
3. **Store it locally** under a conventional directory structure with manifest files, split subdirectories, data files, masks, annotation JSON, and item metadata JSON.
4. **Publish it remotely** by splitting responsibilities across:
   - Hugging Face for dataset repository / manifest / README style coordination
   - GCP for actual data and annotation file blobs
5. **Fetch it back locally** by downloading a manifest first and then lazily filling in missing files.
6. **Load it** by materializing a Hugging Face dataset through a builder and Arrow cache.
7. **Update it incrementally** by comparing against previous versions and copying / merging changed files and annotations.

This gave `mtrix` a practical dataset distribution pipeline with local-first and offline-aware behavior.

### What it did well

The previous Datalake had several real strengths.

#### 1. Good service decomposition

The split into:

- discovery
- provisioning
- synchronization
- loading
- manifest management

was clean and maintainable. The top-level `Datalake` class remained fairly thin while operational complexity lived in focused service classes.

#### 2. Strong dataset-version packaging model

The manifest-driven dataset-version model was well suited to shipping and loading versioned datasets. It gave a clear package boundary for:

- dataset name
- semantic version
- data type
- split structure
- output definitions
- annotation files
- item metadata files

#### 3. Thoughtful local/offline workflow

The explicit `offline_mode` was operationally useful and reflected real needs. The system was clearly designed around:

- local availability
- remote synchronization when needed
- explicit failure when offline constraints prevented an operation

#### 4. Practical incremental update support

The previous design did support version-to-version update flows, including:

- comparing previous and current versions
- uploading only newly introduced files in some cases
- merging annotation content
- applying removals

That is a meaningful capability and should not be dismissed.

#### 5. Strong Hugging Face integration

If the main consumer abstraction is a Hugging Face dataset, the old design was coherent. The builder/cache flow was aligned with a real consumer story.

### Where it breaks down

The limitations of the previous design are structural rather than cosmetic.

#### 1. It is dataset-package centric, not canonical-data centric

The previous design treats the world primarily as:

- dataset names
- dataset versions
- manifests
- split directories
- files inside those directories

That is enough for dataset shipping, but not enough for a reusable canonical data layer.

It does not make the following concepts first-class:

- assets
- storage references independent of local layout
- datums as reusable units of membership
- annotation sets
- atomic annotation records
- multiple storage locations for the same payload

This is the biggest architectural limitation.

#### 2. Annotations are file-based, not first-class records

Annotations in the old system are largely handled as JSON files per split and per dataset version. They can be merged and copied, but they are not modeled as queryable, canonical records.

That creates several limitations:

- weak support for live annotation CRUD
- poor provenance at the per-annotation level
- difficulty representing multiple overlapping annotation layers
- difficulty querying across annotations independently of dataset package boundaries
- difficulty reusing annotation data outside a specific packaged dataset version

This is one of the primary reasons a new version is needed.

#### 3. Local filesystem layout is doing too much work

The old Datalake is heavily coupled to a particular on-disk representation:

- root dataset directories
- `manifest_v*.json`
- `splits/<split>/...`
- images / meshes / point clouds directories
- masks directories
- annotation and item metadata JSON files

This is practical for one packaging format, but too rigid for a general platform. It makes the local layout feel canonical when it should instead be one materialization strategy among several possible representations.

#### 4. Remote storage topology is fixed and overly opinionated

The previous design effectively assumes:

- Hugging Face for registry / discovery / repository concerns
- GCP for blob storage

That hardcodes vendor roles into the design. It does not provide a generalized mount or multi-storage abstraction and cannot naturally support broader deployment patterns such as:

- local scratch + NAS + cloud
- multiple object stores with equivalent roles
- durable on-prem object storage with optional cloud promotion
- storage backends selected by policy rather than by hardcoded class role

This is a major scalability and portability constraint.

#### 5. No generalized storage namespace or mount abstraction

There is no equivalent of a multi-mount `Store` or unified storage facade. The old design has fixed infrastructure roles, not a composable storage model.

That means it cannot naturally express ideas like:

- default mount vs archive mount
- promotion from one backend to another
- object-level location awareness across multiple backends
- later introduction of additional stores without service-level rewrites

#### 6. Reuse and composability are limited

Because the main unit is a packaged dataset version, it is difficult to treat:

- an image asset
- a derived artifact
- a label snapshot
- a shared annotation layer

as reusable canonical pieces that can participate in multiple datasets or workflows.

The previous architecture makes datasets easy to ship, but makes underlying data harder to reuse compositionally.

### Why it cannot scale as the long-term architecture

The prior Datalake can scale operationally to a point, but it does not scale conceptually into a broader Mindtrace data layer.

It breaks down as requirements expand toward:

- multi-backend storage flexibility
- reusable canonical asset identities
- live structured annotation CRUD
- multiple annotation layers and provenance
- dataset derivation by metadata and annotation queries
- multiple downstream applications sharing the same canonical data layer
- clear separation between canonical persistence and export/package forms

In particular, the following become increasingly expensive or awkward in the old design:

#### 1. Querying and editing annotations as data rather than files

When annotations are primarily versioned files inside split directories, operations that should be simple data queries become package manipulation tasks.

#### 2. Treating storage locations as replaceable infrastructure

The old design assumes role-specific backends rather than a generalized storage abstraction. That makes backend evolution more invasive than it should be.

#### 3. Building multiple downstream views over the same canonical data

The old system is optimized for one specific representation: a dataset package that can be loaded into HF datasets. It is much less well suited to producing many different consumers from the same underlying canonical records.

#### 4. Separating logical identity from physical layout

A long-lived datalake should let assets and annotations have stable logical identity independent of the current filesystem or object-store materialization. The previous design does not fully achieve that.

### Why a V2 must be built

A V2 is needed because the next Datalake should be more than a dataset shipping system. It needs to become a canonical persistence and access layer for Mindtrace data.

Concretely, V2 must support:

- object storage that is mount-based rather than hardcoded to fixed remote roles
- canonical asset records separated from physical location
- structured annotation persistence as first-class records
- immutable dataset versions built from reusable lower-level entities
- queryable datums and annotation sets
- export/package formats as derived representations rather than the canonical source of truth

The old `mtrix` Datalake is a useful predecessor, but it is not sufficient as the long-term foundation.

### What V2 needs that the previous design did not have

The proposed V2 direction adds several necessary capabilities.

#### 1. A generalized storage abstraction

V2 needs a storage facade over multiple backends, such as the newer `Store` / mount model, so that storage becomes configurable and composable rather than fixed.

#### 2. Canonical payload identity

V2 needs explicit `StorageRef` and `Asset` entities so payload-bearing objects can be tracked independently of a particular local directory layout.

#### 3. Canonical annotation model

V2 needs first-class annotation entities:

- `AnnotationSource`
- `AnnotationRecord`
- `AnnotationSet`

This is essential for live editing, queryability, provenance, and reuse.

#### 4. Canonical dataset membership unit

V2 needs `Datum` as the reusable unit of dataset membership rather than treating split file listings as the only durable structure.

#### 5. Immutable dataset versions over reusable canonical entities

V2 should keep immutable dataset versions, but they should be built from references to canonical datums, assets, and annotation sets rather than being defined primarily by directory trees and packaged JSON files.

#### 6. Separation between canonical state and export forms

V2 should treat HF datasets, Arrow caches, manifests, packaged split directories, and training exports as materialized views or export forms, not as the canonical persistence model.

### Summary of the retrospective

The previous `mtrix` Datalake solved a real and useful problem:

- provisioning versioned datasets
- synchronizing them between local and remote storage
- building HF-compatible caches
- loading them reliably

That remains valuable.

However, it is best understood as a dataset lifecycle system rather than a complete canonical datalake architecture.

The V2 direction proposed in this document keeps the strongest operational ideas from `mtrix` — service decomposition, versioning, synchronization, offline awareness, and interoperability — while replacing the rigid parts with a more general and durable model based on:

- generalized storage mounts
- canonical asset records
- atomic annotation records and annotation sets
- reusable datums
- immutable dataset versions built as views over canonical entities

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
      "backend": "s3://minio/datalake",
      "version_objects": true,
      "mutable": true
    },
    {
      "name": "gcp",
      "read_only": false,
      "backend": "gs://my-bucket/datalake",
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

## Integration notes

This proposal is intentionally framed as a public Mindtrace design rather than an application-specific integration plan.

A consumer of the Datalake module should be able to:

- store payloads through the storage / asset APIs
- reference canonical Datalake asset IDs from higher-level application records
- use the annotation APIs for live label CRUD when appropriate
- generate dataset exports from canonical assets and annotation records
- promote objects across mounts through storage copy endpoints

This keeps Datalake positioned as the canonical persistence and access layer while allowing downstream applications to remain thin clients over that data model.

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

In short: build the Datalake as a canonical data layer with a narrow, clear contract, not as a one-off app-specific storage helper and not as a giant platform on day one.

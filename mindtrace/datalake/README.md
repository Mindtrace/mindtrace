# Mindtrace Datalake

The Mindtrace Datalake is the canonical data layer for Mindtrace.

It is intended to sit above the lower-level `database` and `registry` modules and provide a unified model for:

- assets and their storage locations
- collections and collection membership
- annotations and annotation provenance
- dataset composition and immutable dataset versions
- data-oriented integration with jobs and cluster execution

This README reflects the **V3 design direction** for the Datalake module while remaining grounded in the current Mindtrace architecture.

## What the Datalake is for

The Datalake exists to answer questions like:

- What assets exist in the system?
- Where do those assets live physically?
- Which collections include them?
- What annotations exist for them, and where did those annotations come from?
- Which immutable dataset version should a training or evaluation run consume?
- How should jobs and cluster-executed workflows read from and write back into canonical data?

The Datalake is therefore more than a dataset loader and more than a storage helper. It is the data model and persistence boundary that higher-level workflows should build on.

## Relationship to other Mindtrace modules

The Datalake is designed to depend on two lower-level modules:

- **`mindtrace.database`** — structured persistence for canonical records
- **`mindtrace.registry`** — versioned object persistence and storage access

And it is designed to integrate with:

- **`mindtrace.jobs`** — execution schemas, queues, and run lifecycle
- **`mindtrace.cluster`** — orchestration and distributed execution

At a high level:

```mermaid
flowchart TD
    DB[database module]
    REG[registry module]

    DB --> DL[datalake module]
    REG --> DL

    JOBS[jobs module] --> CL[cluster module]
    DL --> CL
```

This means:

- the Datalake should not reimplement storage or document persistence itself
- Jobs should remain focused on execution semantics
- Cluster should be the main integration layer between execution and canonical data

## Current implementation status

The Datalake is evolving.

Historically, Mindtrace has had:

- **V1** — the older `mtrix` Datalake, focused on dataset packaging, synchronization, and loading
- **V2** — the current `mindtrace.datalake` implementation, centered on `Datum`, derivation, and query-based access
- **V3** — the design direction now being defined, which expands the Datalake into a fuller canonical data model

The V3 design introduces a clearer set of canonical entities while still building on the useful ideas from V2.

## Canonical V3 concepts

The core V3 concepts are:

- **Collection** — a logical workspace or organizational boundary
- **CollectionItem** — a membership record connecting a collection to an asset
- **AssetRetention** — a retention/stewardship record describing why an asset should continue to exist
- **StorageRef** — a physical storage reference describing where a payload lives
- **Asset** — the canonical logical record for a payload-bearing object
- **AnnotationSource** — structured provenance for annotations
- **AnnotationRecord** — the atomic unit of annotation persistence
- **AnnotationSet** — a grouping of related annotation records
- **Datum** — the reusable unit of dataset membership/composition
- **DatasetVersion** — an immutable dataset view/version
- **DatasetBuilder** — a helper/API concept for constructing new dataset versions

### Entity relationships

```mermaid
erDiagram
    STORAGE_REF ||--|| ASSET : "locates"
    ASSET ||--o{ COLLECTION_ITEM : "included by"
    COLLECTION ||--o{ COLLECTION_ITEM : "contains"
    ASSET ||--o{ ASSET_RETENTION : "retained by"
    COLLECTION ||--o{ ASSET_RETENTION : "may import/pin"
    ASSET ||--o{ DATUM : "used by role refs"
    DATASET_VERSION ||--o{ DATUM : "manifest contains"
    DATASET_VERSION ||--o{ ANNOTATION_SET : "may include"
    ANNOTATION_SET ||--o{ ANNOTATION_RECORD : "contains"
    DATUM ||--o{ ANNOTATION_RECORD : "annotated by"
    ANNOTATION_SOURCE ||--o{ ANNOTATION_RECORD : "source for"
```

## Storage model

The V3 direction assumes a clean separation between:

- **structured records** stored through the `database` module
- **payload-bearing objects** stored through the `registry` module

Examples:

- annotation metadata and collection membership belong in the database layer
- images, masks, artifacts, and other large payloads belong in the registry/storage layer

### Registry mounts

The new registry/store API work introduces declarative mount definitions for storage configuration.

Conceptually, the Datalake should rely on those primitives rather than hardcoding storage backends directly.

Relevant registry concepts now available include:

- `Mount`
- `Registry.from_mount(...)`
- `Registry.mount`
- `Store.from_mounts(...)`
- `Store.add_mount(...)`

Supported mount/backend families include:

- local filesystem
- S3-compatible storage (including MinIO)
- GCS

This is important for the Datalake because it lets storage become:

- configurable
- multi-backend
- environment-aware
- separate from the canonical data model itself

## Annotations

One of the main V3 goals is to treat annotations as first-class canonical data rather than as ad hoc blobs or package files.

The canonical persisted annotation types should support at least:

- `classification`
- `regression`
- `bbox`
- `rotated_bbox`
- `polygon`
- `polyline`
- `ellipse`
- `keypoint`
- `mask`
- `instance_mask`
- `pointcloud_segmentation`

These types preserve compatibility with the older V1 output surface while giving V3 room to support richer annotation workflows.

## Datasets

In V3, datasets should be represented as immutable views over canonical data rather than as the only place where data meaning lives.

### `DatasetVersion`

`DatasetVersion` is the canonical persisted dataset concept.

It should represent:

- a named versioned dataset
- immutable membership over datums
- stable provenance and repeatability

### `DatasetBuilder`

`DatasetBuilder` should remain a separate helper/API concept.

It should be used to:

- stage membership changes
- construct new immutable dataset versions
- provide a friendlier SDK workflow for creating and revising datasets

It should **not** be treated as a canonical persisted entity in the same way as `DatasetVersion`.

## Jobs and Cluster integration

The Datalake should fit cleanly with the Jobs and Cluster modules.

### Jobs

Jobs should define:

- executable task schemas
- run lifecycle
- retries, queueing, and execution behavior

They should not need to own the Datalake’s canonical storage model.

### Cluster

Cluster should be the integration/orchestration layer that:

- resolves Datalake-backed inputs into worker-consumable job inputs
- dispatches jobs
- persists canonical outputs back into the Datalake
- stores raw run artifacts separately when needed

### Important rule

Job/task schemas are **not** the same thing as canonical Datalake schemas.

For example:

- a detection job output may be a convenient execution-time structure
- but canonical persistence should become an `AnnotationSet` plus atomic `AnnotationRecord`s

This keeps execution concerns and data concerns cleanly separated.

## Design principles

The V3 Datalake direction is guided by a few key principles:

1. **Canonical data should outlive individual workflows**
2. **Storage location should be separate from logical identity**
3. **Datasets should be immutable views over reusable underlying entities**
4. **Annotations should be structured, queryable, and provenance-aware**
5. **Collections should not imply destructive ownership of shared assets**
6. **Execution systems should integrate with the Datalake, not define its schema**

## What this README is not

This README is intentionally a conceptual entry point.

It does not try to be:

- a full API reference for every current class or method
- a migration guide for every historical implementation detail
- a complete implementation-status ledger

For the evolving architecture and canonical V3 design discussion, see:

- `docs/datalake-v3-proposal.md`

## Built-in Pascal VOC importer

The Datalake package now includes a built-in importer for **Pascal VOC 2012**.

Current scope:

- VOC **2012** only
- splits: `train`, `val`, `trainval`
- one image -> one `Asset`
- one sample -> one `Datum`
- separate annotation sets for:
  - classification
  - detection
  - segmentation
- segmentation imported from `SegmentationClass` as:
  - one per-class binary mask asset
  - one `mask` annotation record per class present

### CLI usage

After installing the package from a branch or editable checkout:

```bash
mindtrace-datalake-import-pascal-voc \
  --mongo-db-uri "mongodb://mindtrace:mindtrace@localhost:27017" \
  --mongo-db-name "mindtrace" \
  --root-dir "./data/pascal-voc" \
  --split train \
  --dataset-name "pascal-voc-2012-train" \
  --download
```

Or directly as a module:

```bash
python -m mindtrace.datalake.importers.pascal_voc \
  --mongo-db-uri "mongodb://mindtrace:mindtrace@localhost:27017" \
  --mongo-db-name "mindtrace" \
  --root-dir "./data/pascal-voc" \
  --split train \
  --dataset-name "pascal-voc-2012-train" \
  --download
```

### Python API

```python
from mindtrace.datalake import Datalake, PascalVocImportConfig, import_pascal_voc

with Datalake.create(
    mongo_db_uri="mongodb://mindtrace:mindtrace@localhost:27017",
    mongo_db_name="mindtrace",
) as datalake:
    summary = import_pascal_voc(
        datalake,
        PascalVocImportConfig(
            root_dir="./data/pascal-voc",
            split="train",
            dataset_name="pascal-voc-2012-train",
            download=True,
        ),
    )
    print(summary)
```

### Notes

- The importer will reuse an already-downloaded VOC tarball or extracted `VOCdevkit/VOC2012` tree when present.
- Importer-managed image and mask payload writes use overwrite-on-conflict semantics so local retries after failed partial imports are less brittle.
- The importer still fails if the target `DatasetVersion` already exists.

## Datalake service

The Datalake package now also includes a `DatalakeService` class for exposing an `AsyncDatalake` through the Mindtrace `Service` framework (FastAPI + MCP).

Design notes:

- uses `AsyncDatalake` internally rather than the sync `Datalake`
- initialization is lazy with optional startup initialization for live service processes
- service endpoints are registered as typed `TaskSchema`-backed operations
- selected read endpoints are also exposed as MCP tools

Example:

```python
from mindtrace.datalake import DatalakeService

service = DatalakeService.launch(
    host="localhost",
    port=8080,
    mongo_db_uri="mongodb://mindtrace:mindtrace@localhost:27017",
    mongo_db_name="mindtrace",
)

print(service.health())
print(service.dataset_versions_list(dataset_name="surface-defects"))
```

Initial endpoint families include:

- `health`, `summary`, `mounts`
- `objects.*`
- `assets.*`
- `collections.*`
- `collection_items.*`
- `asset_retentions.*`
- `annotation_schemas.*`
- `annotation_sets.*`
- `annotation_records.*`
- `datums.*`
- `dataset_versions.*`

## Near-term development direction

The near-term direction for the Datalake is:

- keep the useful simplicity of the current V2 system
- adopt the newer registry/store mount primitives
- grow toward the V3 canonical entity model
- maintain compatibility with the older V1 semantic surface where needed
- keep the module aligned with `database`, `registry`, `jobs`, and `cluster`

In short, the goal is to make the Datalake the long-term data foundation for Mindtrace: modular, storage-aware, queryable, and capable of supporting richer workflows than earlier iterations.

# Mindtrace Datalake

The Mindtrace Datalake is the canonical data layer for Mindtrace. It sits on **`mindtrace.database`** (structured records) and **`mindtrace.registry`** (object storage and mounts) and exposes a unified model for assets, collections, annotations, and immutable dataset versions.

**Start here**

- **[Happy path](./HAPPY_PATH.md)** — local stack, direct upload, **dataset sync** vs **replication**, and operational caveats.
- **Docker (Mongo + MinIO + `DatalakeService`)** — [docker/datalake/README.md](../../docker/datalake/README.md) at the repository root.

---

## What you can do today

| Area | Role |
|------|------|
| **`DatalakeService`** | HTTP/MCP-facing API over `AsyncDatalake` (typed tasks, FastAPI). |
| **Objects & uploads** | Put bytes in storage (`objects.put` or upload-session flow), then reference them from canonical records. |
| **Canonical model** | Assets, collections, datums, dataset versions, annotations — persisted in Mongo, payloads in configured mounts. |
| **Dataset sync** | Export/import **dataset version** bundles between lakes (`dataset_versions.export`, `import_prepare`, `import_commit`, and **caller-staged** `import_session_*` for cross-store payloads). |
| **Replication** | Metadata-first mirroring and payload lifecycle (`replication.*` tasks — upsert, hydrate, reconcile, status, reclaim). |

**Sync vs replication (short):**

- **Dataset sync** — move a **named, versioned dataset snapshot** as an import/export bundle. Dataset-centric.
- **Replication** — mirror **assets** across lakes with a metadata-first pipeline and optional hydration/reclaim. Asset-centric.

Same-lake **`metadata_only`** transfer policies are supported where implemented; **cross-lake `metadata_only` import is intentionally rejected** until unresolved-placeholder semantics exist. See the [happy path](./HAPPY_PATH.md) and GitHub issues for detail.

---

## Relationship to other Mindtrace modules

- **`mindtrace.database`** — persistence for canonical documents.
- **`mindtrace.registry`** — mounts, stores, and `StorageRef` resolution.
- **`mindtrace.jobs`** / **`mindtrace.cluster`** — execution and orchestration consume datalake data; they should not define the canonical schema.

```mermaid
flowchart TD
    DB[database module]
    REG[registry module]

    DB --> DL[datalake module]
    REG --> DL

    JOBS[jobs module] --> CL[cluster module]
    DL --> CL
```

---

## DataVault (`AsyncDataVault` / `DataVault`)

**DataVault** is a small facade over **`save(alias, payload, …)`** and **`load(alias)`**: it creates/links assets, registers aliases, and reads objects through the same registry stack as **`AsyncDatalake`**.

- **In-process:** `AsyncDataVault(async_datalake)` or `DataVault(datalake)` (or pass an explicit **`LocalAsyncDataVaultBackend`** / **`LocalDataVaultBackend`**).
- **Remote HTTP/MCP:** `cm = DatalakeService.connect(url="http://…")`, then **`DataVault(cm)`** or **`AsyncDataVault(cm)`**. The facade recognizes the service client and uses **`DatalakeServiceDataVaultBackend`** / **`DatalakeServiceAsyncDataVaultBackend`** automatically. You can still pass those backends explicitly if you prefer.

When the lake is running in **Docker** (Mongo + MinIO + `DatalakeService`), see **[docker/datalake/README.md](../../docker/datalake/README.md#using-datavault-against-the-compose-stack)** for a copy-paste sample against `http://localhost:8080`.

---

## Datalake service (`DatalakeService`)

The package provides **`DatalakeService`**, which wraps **`AsyncDatalake`** with the Mindtrace **`Service`** layer (FastAPI + MCP). Initialization can be lazy; live processes may enable startup initialization and background helpers (for example upload-session reconciliation).

Example (adjust host/port and Mongo URIs for your environment):

```python
from mindtrace.datalake import DatalakeService

service = DatalakeService.launch(
    host="localhost",
    port=8080,
    mongo_db_uri="mongodb://localhost:27017",
    mongo_db_name="mindtrace",
)
# Use async handlers or the service’s app/routes per your deployment.
```

### Task families (overview)

Includes, among others:

- **`health`**, **`summary`**, **`mounts`**
- **`objects.*`** — put/get/head/copy, upload session create/complete
- **`assets.*`**, **`assets.get_by_alias`**, **`aliases.add`**, **`collections.*`**, **`collection_items.*`**, **`asset_retentions.*`**
- **`annotation_*`**, **`datums.*`**
- **`dataset_versions.*`** — CRUD, resolve, **export**, **import_prepare**, **import_commit**
- **`replication.*`** — **upsert_batch**, **hydrate_asset_payload**, **reconcile**, **mark_local_delete_eligible**, **delete_local_payload**, **reclaim_verified_payloads**, **status**

Exact wire format and paths depend on how the shared `Service` framework exposes tasks; treat names above as the stable task identifiers.

---

## Storage model

Structured records live in the database layer; large payloads live in registry-backed storage. Mounts can target local disk, S3-compatible endpoints (including MinIO), GCS, etc., via **`Mount`** and store configuration.

---

## Design reference (V3 direction)

The datalake is evolving from earlier internal versions toward a fuller **V3** canonical model. The sections below summarize that direction; they are **not** an exhaustive API spec.

### Implementation status (historical labels)

- **V1** — older `mtrix`-era datalake (packaging and loading).
- **V2** — current `mindtrace.datalake` center of gravity (`Datum`, queries, etc.).
- **V3** — design direction: clearer entities, registry mounts, service-oriented access.

### Canonical V3 concepts

- **Collection**, **CollectionItem**, **AssetRetention**
- **StorageRef**, **Asset**
- **Annotation** schema/set/record model
- **Datum**, **DatasetVersion**
- **DatasetCard** (optional structured documentation attached to a dataset version)
- **DatasetBuilder** (helper for constructing new versions — not the same as a persisted version record)

### Dataset cards

`DatasetVersion.description` is the short summary stored with a version for listings and quick display.
`DatasetVersion.metadata` remains the place for lightweight operational metadata and query keys.
`DatasetVersion.card` is an optional, standalone `DatasetCard` for richer human-facing documentation that should
travel with the immutable dataset version. `DatasetCard.summary` makes the card meaningful when serialized or
displayed independently; it may intentionally duplicate `DatasetVersion.description`.

```python
from mindtrace.datalake import DatasetCard, DatasetProvenance, DatasetStatistic, SplitInfo

card = DatasetCard(
    summary="Binary image classification dataset.",
    task="classification",
    modalities=["image"],
    provenance=DatasetProvenance(
        creation_method="Reviewed image importer",
        included_subsets=["production"],
        excluded_subsets=["repeated observations"],
        split_strategy="Deterministic stratification by class",
        split_seed=42,
        split_key="source_path",
    ),
    splits={
        "train": SplitInfo(count=1200, percentage=85.7),
        "val": SplitInfo(count=200, percentage=14.3),
    },
    summary_statistics=[DatasetStatistic(name="total_items", value=1400, unit="items")],
    evaluation_notes=["Evaluate rare classes separately"],
    intended_uses=["Train and validate image classifiers"],
    limitations=["Small validation split"],
    markdown="## Notes\n\nImported from the reviewed production subset.",
)

datalake.create_dataset_version(
    dataset_name="demo-images",
    version="1.0.0",
    manifest=datum_ids,
    card=card,
)
```

### Entity relationships (conceptual)

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

### Annotations

V3 aims for first-class annotation types (classification, bbox, mask, keypoint, etc.) with provenance. See `docs/datalake-v3-proposal.md` in the repository for the full proposal.

### Design principles

1. Canonical data should outlive individual workflows.
2. Storage location should be separate from logical identity.
3. Datasets should be immutable views over reusable entities.
4. Annotations should be structured, queryable, and provenance-aware.
5. Collections should not imply destructive ownership of shared assets.
6. Execution systems integrate with the datalake; they do not define its schema.

---

## Built-in Pascal VOC importer

The package includes an importer for **Pascal VOC 2012** (splits, one image per asset, segmentation via class masks, etc.). This is **one** way to load a benchmark into the canonical model; it is separate from service upload/sync/replication flows.

### CLI

```bash
mindtrace-datalake-import-pascal-voc \
  --mongo-db-uri "mongodb://mindtrace:mindtrace@localhost:27017" \
  --mongo-db-name "mindtrace" \
  --root-dir "./data/pascal-voc" \
  --split train \
  --dataset-name "pascal-voc-2012-train" \
  --download
```

Or:

```bash
python -m mindtrace.datalake.importers.pascal_voc \
  --mongo-db-uri "mongodb://mindtrace:mindtrace@localhost:27017" \
  --mongo-db-name "mindtrace" \
  --root-dir "./data/pascal-voc" \
  --split train \
  --dataset-name "pascal-voc-2012-train" \
  --download
```

### Python

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

Importer notes: reuses downloaded trees when present; overwrite-on-conflict for importer writes; fails if the target `DatasetVersion` already exists.

---

## Jobs and cluster

Jobs should own execution lifecycle; cluster orchestration should resolve datalake inputs/outputs. Task output schemas are not canonical datalake schemas — persist results as datalake entities (e.g. annotation sets/records) when they represent durable data.

---

## What this README is not

This file is an entry point, not a full API reference. For deeper V3 discussion see **`docs/datalake-v3-proposal.md`**. For a practical walkthrough of today’s features, use **[HAPPY_PATH.md](./HAPPY_PATH.md)**.

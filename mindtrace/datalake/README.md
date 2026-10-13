# Mindtrace Datalake

The Mindtrace Datalake is the canonical data layer for Mindtrace. It sits on **`mindtrace.database`** (structured records) and **`mindtrace.registry`** (object storage and mounts) and exposes a unified model for assets, collections, annotations, and immutable dataset versions.

**Start here**

- **[Happy path](./HAPPY_PATH.md)** — local stack, direct upload, **dataset sync** vs **replication**, and operational caveats.
- **Docker (Mongo + RustFS + `DatalakeService`)** — [docker/datalake/README.md](../../docker/datalake/README.md) at the repository root.

---

## What you can do today

| Area | Role |
|------|------|
| **`DatalakeService`** | HTTP/MCP-facing API over `AsyncDatalake` (typed tasks, FastAPI). |
| **Objects & uploads** | Put bytes in storage (`objects.put` or upload-session flow), then reference them from canonical records. |
| **Canonical model** | Assets, collections, datums, dataset versions, annotations — persisted in Mongo, payloads in configured mounts. |
| **Training exports** | Typed, relocatable Hugging Face exports for classification, detection, and segmentation. |
| **PyTorch adapters** | Build split-aware, indexable Datasets and ready-to-train DataLoaders from saved Hugging Face exports. |
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

When the lake is running in **Docker** (Mongo + RustFS + `DatalakeService`), see **[docker/datalake/README.md](../../docker/datalake/README.md#using-datavault-against-the-compose-stack)** for a copy-paste sample against `http://localhost:8080`.

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
    mongo_db_name="datalake",
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
- **DatasetBuilder** (helper for constructing new versions — not the same as a persisted version record)

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

## Hugging Face training exports

The Datalake can materialize immutable DatasetVersions as typed, relocatable Hugging Face `Dataset` or `DatasetDict`
artifacts. Training consumes the saved artifact and does not require a live MongoDB, object store, or Datalake
connection:

```text
Datalake DatasetVersion
        ↓ typed Hugging Face export
relocatable Dataset / DatasetDict
        ↓ build_datasets(...)
train / val / test native HF Datasets with PyTorch transforms
        ↓ build_dataloaders(...)
train / val / test PyTorch DataLoaders
```

Dataset and DataLoader builders belong to `mindtrace.models.training`. See the
[Models data-adapter guide](../models/mindtrace/models/training/README.md#hugging-face-data-adapters)
for the supported task profiles and consumption API.

Semantic-segmentation exports store artifact-level semantics in `mindtrace_metadata.json`.
New exports use a flat JSON object with `schema_version: 2`; read it separately using
[`read_export_metadata`](../models/mindtrace/models/training/README.md#export-metadata).
The reader also accepts existing nested v1 sidecars without re-exporting the dataset.

### Included example datasets

The check marks show the tasks and splits supported by the bundled importers. VOC has no public labeled 2012 test
split. Penn-Fudan has no official splits, so its importer creates a deterministic filename-hash train/validation
split.

<table>
  <thead>
    <tr>
      <th rowspan="2">Dataset</th>
      <th colspan="5">Tasks</th>
      <th colspan="3">Splits</th>
    </tr>
    <tr>
      <th>Single-label classification</th>
      <th>Multi-label classification</th>
      <th>Detection</th>
      <th>Semantic segmentation</th>
      <th>Instance segmentation</th>
      <th>Train</th>
      <th>Val</th>
      <th>Test</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>Oxford Flowers102</td>
      <td>✅</td>
      <td></td>
      <td></td>
      <td></td>
      <td></td>
      <td>✅</td>
      <td>✅</td>
      <td>✅</td>
    </tr>
    <tr>
      <td>Pascal VOC 2012</td>
      <td>✅</td>
      <td>✅</td>
      <td>✅</td>
      <td>✅</td>
      <td></td>
      <td>✅</td>
      <td>✅</td>
      <td></td>
    </tr>
    <tr>
      <td>Penn-Fudan Pedestrian</td>
      <td></td>
      <td></td>
      <td></td>
      <td></td>
      <td>✅</td>
      <td>✅</td>
      <td>✅</td>
      <td></td>
    </tr>
  </tbody>
</table>

- **Flowers102** imports its official train, validation, and test splits into one immutable DatasetVersion.
- **Pascal VOC 2012** creates a canonical union and task-specific DatasetVersions in one pass. Detection and
  whole-image multi-label classification use the Main split. Single-label classification reuses the Main image
  Datums and crops each bounding box during export. Semantic segmentation uses the independent Segmentation split
  and preserves background ID `0` and ignore ID `255`. For VOC train, the 5,717 Main images and 1,464 Segmentation
  images overlap by 1,151, so the canonical union stores 6,030 unique JPEG Assets once.
- **Penn-Fudan Pedestrian** contains 170 images and 345 pedestrian instances. Each image and indexed mask PNG is
  stored once. The HF export materializes per-object binary masks, and the runtime adapter returns torchvision
  Mask R-CNN targets.

### Import and export example

Install all optional importer, Hugging Face, and PyTorch dependencies from the monorepo root:

```bash
uv sync --all-extras --dev
```

Start a local MongoDB container:

```bash
docker run --detach \
  --name mindtrace-datalake-mongodb \
  --publish 27017:27017 \
  mongo:7
```

The examples use the `datalake` database. Remove the container afterward with:

```bash
docker rm --force mindtrace-datalake-mongodb
```

#### Import Flowers102, VOC, and Penn-Fudan

```python
from pathlib import Path

from mindtrace.core import Config
from mindtrace.datalake import (
    Datalake,
    Flowers102ImportConfig,
    PascalVocImportConfig,
    PennFudanImportConfig,
    import_flowers102,
    import_pascal_voc,
    import_penn_fudan,
)

mindtrace_temp = Path(Config().MINDTRACE_DIR_PATHS.TEMP_DIR).expanduser()
data_root = mindtrace_temp / "datasets"
export_root = mindtrace_temp / "exports"

data_root.mkdir(parents=True, exist_ok=True)
export_root.mkdir(parents=True, exist_ok=True)

with Datalake.create(
    mongo_db_uri="mongodb://localhost:27017",
    mongo_db_name="datalake",
) as datalake:
    import_flowers102(
        datalake,
        Flowers102ImportConfig(
            root_dir=data_root / "flowers102",
            dataset_name="flowers-102",
            splits=("train", "val", "test"),
            download=True,
        ),
    )

    import_pascal_voc(
        datalake,
        PascalVocImportConfig(
            root_dir=data_root / "pascal-voc-2012",
            dataset_name="pascal-voc-2012-train",
            split="train",
            download=True,
        ),
    )

    import_penn_fudan(
        datalake,
        PennFudanImportConfig(
            root_dir=data_root / "penn-fudan",
            download=True,
            val_fraction=0.2,
            split_seed=42,
        ),
    )
```

Importers create immutable DatasetVersions and fail if the target name/version already exists. The downloaded source
trees are reusable, but rerunning the import requires new target versions or a clean Datalake.

#### Export every supported task

This cell uses persisted names and versions, so it remains usable after a Python or notebook restart:

```python
from pathlib import Path

from mindtrace.core import Config
from mindtrace.datalake import Datalake

mindtrace_temp = Path(Config().MINDTRACE_DIR_PATHS.TEMP_DIR).expanduser()
export_root = mindtrace_temp / "exports"
export_root.mkdir(parents=True, exist_ok=True)

exports = {
    "flowers102-single-label": (
        "flowers-102",
        "1.0.0",
        {"task": "classification"},
    ),
    "voc-single-label": (
        "pascal-voc-2012-train-classification-single-label",
        "1.2.1",
        {"task": "classification"},
    ),
    "voc-multi-label": (
        "pascal-voc-2012-train-classification-multi-label",
        "1.2.1",
        {"task": "classification"},
    ),
    "voc-detection": (
        "pascal-voc-2012-train-detection",
        "1.2.1",
        {"task": "detection"},
    ),
    "voc-semantic-segmentation": (
        "pascal-voc-2012-train-semantic-segmentation",
        "1.2.1",
        {"task": "segmentation"},
    ),
    "penn-fudan-instance-segmentation": (
        "penn-fudan-ped",
        "1.0.0",
        {"task": "segmentation"},
    ),
}

with Datalake.create(
    mongo_db_uri="mongodb://localhost:27017",
    mongo_db_name="datalake",
) as datalake:
    for destination_name, (dataset_name, dataset_version, options) in exports.items():
        datalake.export_dataset_version_to_format(
            dataset_name,
            dataset_version,
            format="huggingface",
            destination=export_root / destination_name,
            include_media=True,
            overwrite=True,
            exporter_options=options,
        )
```

The exports embed media for relocation, preserve ordered class mappings and source lineage, and normalize task
records into stable HF schemas.

For a DatasetVersion with multiple logical classification annotations, select one field by its exact annotation
attributes. When the selected annotations do not have label IDs, provide an explicit class order. Required top-level
row metadata can be copied into typed fields in the same export pass.

The exporter options `annotation_attributes`, `class_names` (or `classification_class_names`), and `metadata_keys`
are supported only for `task="classification"`, `classification_type="single_label"`, and
`classification_source="annotations"`. The latter two default to these values unless overridden by dataset metadata.
Supplying any of these option keys on bbox-crop, multi-label, detection, segmentation, or generic export paths raises
`ValueError` before the destination is prepared, even if the option value is empty or `None`. Other typed paths
continue to obtain class names from dataset metadata; they do not project custom metadata columns. Loader
`metadata_keys` requests require columns already present in the saved artifact.

For example:

```python
datalake.export_dataset_version_to_format(
    "multi-field-classification",
    "1.0.0",
    format="huggingface",
    destination=export_root / "selected-classification",
    include_media=True,
    exporter_options={
        "task": "classification",
        "annotation_attributes": {"field": "primary_target"},
        "class_names": ["negative", "positive"],
        "metadata_keys": {
            "subject_id": "string",
            "group_id": "string",
        },
    },
)
```

The attribute mapping is matched exactly against classification records, and every item must have exactly one
match. Metadata keys refer to required, top-level Datum metadata; the key name is preserved in the Hugging Face
artifact. Supported scalar dtypes are `string`, `bool`, signed and unsigned integer widths from 8 through 64 bits,
and `float16`, `float32`, and `float64`. The resolved selector and metadata-key types are recorded in
`mindtrace_metadata.json` and available through `read_export_metadata(export_path)`. The ordered classification
names are stored in `dataset.features["label"].names`; their positions define the label IDs, so the sidecar does
not duplicate that mapping. The `class_names` export option still controls this order. Existing exports without
these options are unchanged.

Requested metadata values are validated against the declared Arrow type while each row is prepared. Integer
values must fit the declared signed/unsigned width; floats are not truncated into integers and booleans are not
accepted as numbers. Conversion errors identify the source asset, metadata key, and requested dtype. Missing or
null requested values remain errors.

#### Consume the exported artifacts

Continue with the [Models training guide](../models/mindtrace/models/training/README.md#build-datasets-and-dataloaders)
for dataset/DataLoader construction, transforms, batching, and runtime target contracts.

---

## Jobs and cluster

Jobs should own execution lifecycle; cluster orchestration should resolve datalake inputs/outputs. Task output schemas are not canonical datalake schemas — persist results as datalake entities (e.g. annotation sets/records) when they represent durable data.

---

## What this README is not

This file is an entry point, not a full API reference. For deeper V3 discussion see **`docs/datalake-v3-proposal.md`**. For a practical walkthrough of today’s features, use **[HAPPY_PATH.md](./HAPPY_PATH.md)**.

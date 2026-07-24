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

## Flowers102 classification import, export, and DataLoaders

Flowers102 provides native `train`, `val`, and `test` splits. The importer stores all selected splits in one
immutable `DatasetVersion`, with one image asset and one single-label classification record per datum. Labels use
the canonical Oxford 102 category names in the source dataset's zero-based target order, and that ordered mapping is
preserved in the Hugging Face `ClassLabel` feature.

Install the optional source and training dependencies:

```bash
pip install "mindtrace-datalake[import-flowers102,dataloaders]"
```

Import the dataset:

```python
from mindtrace.datalake import Datalake, Flowers102ImportConfig, import_flowers102

with Datalake.create(
    mongo_db_uri="mongodb://mindtrace:mindtrace@localhost:27017",
    mongo_db_name="mindtrace",
) as datalake:
    summary = import_flowers102(
        datalake,
        Flowers102ImportConfig(
            root_dir="./data/flowers102",
            download=True,
        ),
    )
```

The equivalent CLI is:

```bash
mindtrace-datalake-import-flowers102 \
  --mongo-db-uri "mongodb://mindtrace:mindtrace@localhost:27017" \
  --mongo-db-name "mindtrace" \
  --root-dir "./data/flowers102" \
  --download
```

Export the resulting classification dataset to a typed, relocatable Hugging Face `DatasetDict`:

```python
with Datalake.create(
    mongo_db_uri="mongodb://mindtrace:mindtrace@localhost:27017",
    mongo_db_name="mindtrace",
) as datalake:
    datalake.export_dataset_version_to_format(
        "flowers-102",
        "1.0.0",
        format="huggingface",
        destination="./exports/flowers102",
        exporter_options={"task": "classification"},
    )
```

Then construct split-aware PyTorch loaders from the export:

```python
from mindtrace.datalake import build_dataloaders
from torchvision import transforms

# Select preprocessing that matches the model being trained. Flowers102
# images have varying dimensions, so batched loading requires a transform
# that produces a consistent tensor shape.
image_transform = transforms.Compose(
    [
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
    ]
)

loaders = build_dataloaders(
    "./exports/flowers102",
    task="classification",
    transforms=image_transform,
    batch_size=32,
    num_workers=4,
    seed=42,
)

train_loader = loaders["train"]
val_loader = loaders["val"]
test_loader = loaders["test"]
```

Pass either one transform or a split-to-transform mapping through `transforms=`. The transform should implement the
resize, rescaling, and normalization contract expected by the selected model; train-only augmentation can be supplied
separately from deterministic validation and test transforms. Training data is shuffled; validation and test data are
not. COCO does not define a portable image-classification contract, so classification-only datasets raise a clear
error when exported with `format="coco"`.

---

## Built-in Pascal VOC importer

The package includes a one-pass importer for **Pascal VOC 2012**. By default it imports classification, detection,
and semantic segmentation together and creates task-specific immutable DatasetVersions. VOC defines its Main and
Segmentation train splits independently: Main contains 5,717 images, Segmentation contains 1,464, and 1,151 occur in
both. The combined train import therefore stores their union of 6,030 source JPEGs exactly once. Detection and
multi-label classification views reference the 5,717 Main Datums; semantic segmentation references its 1,464 Datums;
single-label classification uses lightweight region Datums that reference the same JPEG Assets.

Semantic segmentation preserves each original categorical mask, including background ID `0` and ignore ID `255`.
The optional `tasks=(...)` setting limits which annotations and views are created. Set
`create_task_versions=False` (or pass `--no-task-versions` to the CLI) to create only the canonical version.

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
    print(summary.dataset_names)
```

Importer notes: reuses downloaded trees when present; supports immutable registries; fails if the target
`DatasetVersion` already exists. All output version names are preflighted before any Assets are written.

Export VOC detections to a typed Hugging Face dataset and build variable-target PyTorch loaders:

```python
datalake.export_dataset_version_to_format(
    summary.dataset_names["detection"],
    summary.dataset_version,
    format="huggingface",
    destination="./exports/voc-detection",
    exporter_options={"task": "detection"},
)

loaders = build_dataloaders(
    "./exports/voc-detection",
    task="detection",
    batch_size=8,
)
```

Detection exports embed images and use an `objects` sequence with pixel-space `xywh` boxes, area, and a contiguous
zero-based `ClassLabel`. Source label IDs such as VOC's one-based IDs are remapped by class name during export. A
detection loader converts boxes to the `xyxy` tensors expected by torchvision models. Its transform receives
`(image, target)` and must return the transformed pair so boxes stay aligned with image geometry. The detection
collator returns image and target lists because object counts vary between samples.

The native VOC whole-image task is multi-label. It exports one 20-element multi-hot float target per image:

```python
datalake.export_dataset_version_to_format(
    summary.dataset_names["classification_multi_label"],
    summary.dataset_version,
    format="huggingface",
    destination="./exports/voc-multi-label",
    exporter_options={
        "task": "classification",
        "classification_type": "multi_label",
    },
)
```

The single-label view contains one lightweight region Datum per bounding box. Each region references its source JPEG;
the HF exporter performs the crop while materializing the row. The row retains `source_image_asset_id`,
`source_annotation_id`, and the source `xywh` bbox. Regions inherit the source image's split, preventing
train/validation leakage:

```python
datalake.export_dataset_version_to_format(
    summary.dataset_names["classification_single_label"],
    summary.dataset_version,
    format="huggingface",
    destination="./exports/voc-object-crops",
    exporter_options={"task": "classification"},
)
```

Both exports use the classification DataLoader. Classification images vary in size, so provide a transform that
produces a fixed tensor shape:

```python
from torchvision import transforms

image_transform = transforms.Compose(
    [
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
    ]
)

multi_label_loaders = build_dataloaders(
    "./exports/voc-multi-label",
    task="classification",
    transforms=image_transform,
    batch_size=32,
)
crop_loaders = build_dataloaders(
    "./exports/voc-object-crops",
    task="classification",
    transforms=image_transform,
    batch_size=32,
)
```

Single-label targets are scalar `LongTensor`s suitable for cross entropy. Multi-label targets are 20-element
`FloatTensor`s suitable for binary cross entropy with logits. VOC classification flags greater than zero are treated
as positive; absent and difficult/ambiguous flags are currently represented as zero. VOC provides `train` and `val`
labels but no public labeled test split.

Export and load the semantic segmentation subset created by the same import:

```python
datalake.export_dataset_version_to_format(
    summary.dataset_names["semantic_segmentation"],
    summary.dataset_version,
    format="huggingface",
    destination="./exports/voc-semantic",
    exporter_options={"task": "semantic_segmentation"},
)

semantic_loaders = build_dataloaders(
    "./exports/voc-semantic",
    task="semantic_segmentation",
    batch_size=8,
)
```

Semantic samples are `(image, mask)` pairs where the image is a float tensor and the mask is a long tensor containing
class IDs `0..20` and ignore ID `255`. The default collator keeps variable-resolution images and masks as lists. A
paired transform may resize/crop both before collation; masks must use nearest-neighbour interpolation.

---

## Jobs and cluster

Jobs should own execution lifecycle; cluster orchestration should resolve datalake inputs/outputs. Task output schemas are not canonical datalake schemas — persist results as datalake entities (e.g. annotation sets/records) when they represent durable data.

---

## What this README is not

This file is an entry point, not a full API reference. For deeper V3 discussion see **`docs/datalake-v3-proposal.md`**. For a practical walkthrough of today’s features, use **[HAPPY_PATH.md](./HAPPY_PATH.md)**.

# Datalake happy path

This guide walks through the main ways to use the datalake **today**: run a local stack, put bytes in object storage, build canonical records, move **dataset versions** between lakes (sync), and run **replication** (metadata-first offload) with optional payload hydration and reclaim.

It complements the conceptual overview in [README.md](./README.md). For container bring-up details, see [docker/datalake/README.md](../../docker/datalake/README.md) at the repository root.

---

## 1. Run a local datalake (Mongo + MinIO + service)

From the **repository root**:

```bash
cp docker/datalake/.env.example docker/datalake/.env
docker compose -f docker/datalake/docker-compose.yml --env-file docker/datalake/.env up --build
```

Defaults expose:

- **DatalakeService** at `http://localhost:8080`
- **MinIO** S3 API at `http://localhost:9000` (console on `9001`)

The service image configures a single default S3 mount (see env vars in `docker/datalake/.env.example`). Adjust hostnames if you call the API from the host versus from another container.

---

## 2. Confirm the service is alive

Use the service’s **`health`** task (exact HTTP path depends on how `DatalakeService` is mounted in the Mindtrace `Service` framework). A successful check proves Mongo initialization and routing work.

The **`summary`** and **`mounts`** tasks are useful for quick introspection of the lake and configured registry mounts.

---

## 3. Direct upload: control plane vs data plane

The datalake separates:

- **Object storage** — blobs live in the registry/store (e.g. MinIO via a named mount).
- **Canonical records** — assets, datums, dataset versions, etc. live in Mongo via `AsyncDatalake`.

Typical flow:

1. **Write bytes** — `objects.put` (small payloads) or **`objects.upload_session.create`** / **`objects.upload_session.complete`** (larger or presigned-style flows).
2. **Create or attach an asset** — e.g. **`assets.create`** with a `StorageRef` pointing at the uploaded object, or **`assets.create_from_object`** when the service accepts inline bytes.

You can then **`collections.*`**, **`datums.*`**, and **`dataset_versions.*`** to organize data into immutable dataset versions.

---

## 4. Dataset sync (import/export) — versioned bundles

**Dataset sync** moves an immutable **dataset version** (and related graph) as a bounded **export bundle** from one lake and **imports** it into another.

Service surface:

- **`dataset_versions.export`** — build a bundle from a named dataset version on the **source** lake.
- **`dataset_versions.import_prepare`** — compute a plan (idempotency, mapping).
- **`dataset_versions.import_commit`** — apply the import on the **target** lake.

**Mental model:** this is “ship a dataset version snapshot,” not continuous byte replication.

**Important limitation:** **`transfer_policy="metadata_only"`** is only supported when source and target refer to the **same** datalake instance. Cross-lake `metadata_only` imports are **rejected** on purpose today, because target `StorageRef` values must remain resolvable unless the system gains explicit placeholder/unresolved semantics. See GitHub issue discussion in the repo for future design.

---

## 5. Replication (one-way, metadata-first) — separate from sync

**Replication** is a **different pipeline** from dataset sync. It is designed for **metadata-first** mirroring of assets (and related state) from a **source** lake to a **target** lake, then optional **payload hydration**, verification, and **reclaim** of source-side bytes.

Rough lifecycle:

| Stage | Purpose |
|--------|---------|
| **`replication.upsert_batch`** | Push replicated metadata into the target (placeholder / mirrored records). |
| **`replication.hydrate_asset_payload`** | Materialize bytes on the target when ready. |
| **`replication.reconcile`** | Drive pending/failed payload work on the target. |
| **`replication.status`** | Inspect overall replication status (may scan broadly today). |
| **`replication.mark_local_delete_eligible`** | Mark source-side delete eligibility after remote verification. |
| **`replication.delete_local_payload`** / **`replication.reclaim_verified_payloads`** | Remove local payload bytes when policy allows. |

Operational state for replication is currently carried in **asset metadata** (e.g. under `metadata["replication"]`). Dedicated persistence for replication jobs is planned separately; see tracking issues in the GitHub repo.

**Contrast with sync:**

- **Sync** — import/export **dataset versions** as coherent bundles (dataset-centric).
- **Replication** — mirror **assets** and payload lifecycle across lakes (asset-centric, metadata-first).

---

## 6. Tombstones and deleted payloads

After reclaim, a source asset may carry a **tombstone** `StorageRef` (for example mount `__local_payload_deleted__`) so the record is not left pointing at live storage. That mount is **not** a real registry mount; dereferencing it through normal object APIs should fail (for example with a store “location not found” style error). Treat it as an explicit “payload removed” marker, not a readable path.

---

## 7. Optional: Pascal VOC importer

For a dataset-centric import from a classic benchmark, the package still ships a **Pascal VOC 2012** importer (CLI and Python). See [README.md § Built-in Pascal VOC importer](./README.md#built-in-pascal-voc-importer).

---

## 8. Where to go next

- **Architecture and V3 concepts** — [README.md](./README.md)
- **V3 proposal (long-form)** — `docs/datalake-v3-proposal.md` in the repository
- **Docker stack** — [docker/datalake/README.md](../../docker/datalake/README.md)

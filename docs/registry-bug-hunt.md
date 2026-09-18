# Registry bug hunt — agent handoff

This document is for a second agent (or reviewer) to **verify the issues**, not to implement fixes yet unless asked.

Branch: `feature/registry-bug-hunt` (from `dev`). **No production code was changed.** Only failing-until-fixed contract tests (and this note) were added.

The review was source-driven, then proven with tests against local backends (unit) and MinIO/GCS (integration). Do not treat existing tests that document surprising behavior as the intended contract; the new `*BugHunt` classes encode the intended contract.

---

## How to re-run

Existing registry unit tests were green **before** these additions (`ds test: --unit registry`, 617 passed).

New unit tests (local temp-dir backends; expected mostly fail until fixed):

```bash
ds test: \
  tests/unit/mindtrace/registry/core/test_store.py::TestStoreBugHunt \
  tests/unit/mindtrace/registry/core/test_registry.py::TestRegistryBugHunt \
  tests/unit/mindtrace/registry/backends/test_s3_registry_backend.py::TestS3RegistryBackendBugHunt \
  tests/unit/mindtrace/registry/backends/test_gcp_registry_backend.py::TestGCPRegistryBackendBugHunt
```

Last run: **28 failed, 2 passed**.

New integration tests (MinIO via Docker + optional GCS credentials; parametrized `minio` / `gcp`):

```bash
ds test: \
  tests/integration/mindtrace/registry/core/test_registry_remote_cache_integration.py \
  tests/integration/mindtrace/registry/core/test_store_remote_integration.py
```

Last run: **11 failed, 1 passed** (C1 MinIO passed; everything else failed). GCS setup/teardown is slow (~3.5 min for 12 tests).

Do **not** require a full `ds test` for verification. Integration needs MinIO (`MINDTRACE_MINIO__*`); GCS skips without credentials.

---

## What already holds (do not “fix” these)

| Test | Contract |
|---|---|
| `TestStoreBugHunt.test_pop_without_version_deletes_all_versions` | Store `pop("name")` deletes **all** versions, returns latest. |
| `TestRegistryBugHunt.test_load_with_unimportable_class_still_returns_json_container` | **M2** — missing `class` metadata falls back without `issubclass(Any, dict)` crashing. |

Registry `pop("name")` deleting **only latest** is the bug; Store is the reference.

---

## Issue map

IDs (S/R/C/B/M) are from the original hunt. Tests live in:

| Class | File |
|---|---|
| `TestStoreBugHunt` | `tests/unit/mindtrace/registry/core/test_store.py` |
| `TestRegistryBugHunt` | `tests/unit/mindtrace/registry/core/test_registry.py` |
| `TestS3RegistryBackendBugHunt` | `tests/unit/mindtrace/registry/backends/test_s3_registry_backend.py` |
| `TestGCPRegistryBackendBugHunt` | `tests/unit/mindtrace/registry/backends/test_gcp_registry_backend.py` |
| `TestRegistryRemoteCacheBugHunt` | `tests/integration/mindtrace/registry/core/test_registry_remote_cache_integration.py` |
| `TestStoreRemoteBugHunt` | `tests/integration/mindtrace/registry/core/test_store_remote_integration.py` |

Fixtures for the last two: `tests/integration/mindtrace/registry/core/conftest.py` (MinIO first, GCS with `pytest.mark.gcp`).

---

## 1. Names are not opaque IDs

**Bug.** Object names are treated as filesystem paths, glob patterns, *and* Store keys. `models/resnet` is a name until a mount named `models` exists, then it is `mount=models` + `name=resnet`. Metadata files are `_meta_{name}@{version}` with `/` and `*` left raw. Listing uses `Path.stem` and `glob()`, so slashes truncate and `*` matches other objects.

**Tests (all failed unless noted)**

| ID | Test | Observed |
|---|---|---|
| S1 | `TestStoreBugHunt.test_slash_key_parse_is_stable_when_a_matching_mount_is_added` | After `add_mount("nested")`, `nested/path` parses as mount `nested` + name `path`. |
| B1 | `TestRegistryBugHunt.test_list_objects_includes_names_containing_slashes` | `load("models/resnet")` looks up `models/resnet@` (empty version). Worse than listing-only. |
| B2 | `TestS3RegistryBackendBugHunt.test_list_objects_preserves_slash_in_object_names` | Listed `['resnet']` not `models/resnet`. |
| B2 | `TestGCPRegistryBackendBugHunt.test_list_objects_preserves_slash_in_object_names` | Same. |
| B3 | `TestRegistryBugHunt.test_list_versions_treats_glob_metacharacters_in_names_as_literal` | `list_versions("foo*")` → `['.0.0', '1.0.0']`. |

**Suggested fix.** Identity is `(mount, name, version)` as three fields. Names are opaque (no `/`, `@`, or glob meaning in the ID). Encode them in storage keys. Never parse a mount out of `name`. If slashy display names are wanted, store them in metadata. Listing is prefix/equality on encoded keys, not `glob` on a user string.

---

## 2. Store reads and writes use different address spaces

**Bug.** `load` / `has_object` / `__contains__` search every mount. `save` / `delete` / `move` / `create_direct_download_url` / `commit_direct_upload` send unqualified keys to `default_mount`. One string key, two APIs.

**Tests**

| ID | Test | Observed |
|---|---|---|
| S2 | `TestStoreBugHunt.test_unqualified_delete_removes_the_object_load_would_return` | `delete("item")` hits default; object on `b` remains. |
| S2 | `TestStoreBugHunt.test_unqualified_save_does_not_make_an_existing_name_unreadable` | Second save goes to default; `load("item")` → `StoreAmbiguousObjectError`. |
| S2 | `TestStoreRemoteBugHunt.test_s2_unqualified_direct_download_url_uses_discovered_mount` [minio, gcp] | Failed on the **control** `create_direct_download_url("local/{name}")`: local mount raised `RegistryObjectNotFound` instead of `None`. Never reached the unqualified-presign assertion. Still demonstrates default-mount routing. |
| S4 | `TestStoreBugHunt.test_unqualified_move_to_same_name_relocates_onto_default_mount` | Copy onto default, then resolve is ambiguous. |
| S5 | `TestStoreBugHunt.test_contains_true_implies_getitem_succeeds` | `"shared" in store` is True; `store["shared"]` raises `StoreAmbiguousObjectError`. |
| S7 | `TestStoreBugHunt.test_update_from_store_does_not_drop_same_named_objects_from_different_mounts` | Both source `item`s flatten onto default; `RegistryVersionConflict`. |

**Suggested fix.** One resolver for every operation: qualified key → that mount; unqualified → unique match across mounts, else ambiguous / not-found (same as load). Writes must not invent a home on `default_mount` unless the name is new. `update` copies `mount/name@version`. Presign, delete, and move use that resolver. Alternative: require an explicit mount on all writes and drop unqualified mutation.

Local `create_direct_download_url` returning `None` (cannot presign) vs raising not-found should be made consistent as part of this.

---

## 3. Version is a mode, not part of identity

**Bug.** Unversioned registries ignore the version argument. Versioned registries do not share one `resolve_version()`. `in` normalizes `"x@1"`; `del` does not. `load("latest")` resolves; `del["x@latest"]` does not. Registry `pop("name")` deletes only latest; Store deletes all. Batch autoincrement assigns the same next version twice. Missing explicit delete often succeeds. `_latest` is a process-local TTL cache.

**Tests**

| ID | Test | Observed |
|---|---|---|
| R2 | `test_unversioned_has_object_does_not_ignore_requested_version` | `has_object("x","9.9.9")` is True. |
| R2 | `test_unversioned_load_does_not_ignore_requested_version` | `load("x","9.9.9")` returns version 1. |
| R2 | `test_unversioned_save_does_not_silently_rewrite_explicit_version` | `save(..., version="2.0.0")` stores `1.0.0`. |
| R3 | `test_unversioned_delete_of_missing_name_raises` | Missing delete is silent success. |
| R5 | `test_batch_save_same_name_autoincrement_assigns_distinct_versions` | Both items resolve to `1.0.0`; skip + failure. |
| R7 | `test_delitem_normalizes_short_version_strings` | `"x@1" in registry` True; `del registry["x@1"]` looks up raw `"1"`. |
| R8 | `test_delitem_resolves_latest_sentinel` | `del registry["x@latest"]` does not resolve latest. |
| — | `TestRegistryBugHunt.test_pop_without_version_deletes_all_versions` | Only latest deleted; `1.0.0` remains. |
| B4 | `test_delete_missing_explicit_version_raises` | Missing version delete does not raise. |
| C5 | `test_versions_cache_does_not_hide_writes_from_another_instance` | After writer saves `2.0.0`, reader `load("latest")` still returns `1`. |
| C2 | `TestRegistryRemoteCacheBugHunt.test_c2_...` [minio, gcp] | `load("latest")` returned `1` not `2`. Race wrapper likely never saw version `"latest"` because remote load used already-resolved `1.0.0`. **Did not fully prove** “cache new bytes under old version”; still shows latest resolution / TOCTOU shape. Re-check the wrapper vs `_load_single_cached` before treating C2 as closed. |

**Suggested fix.** Always persist a concrete version. Unversioned mode is a single slot (`1.0.0`), not “ignore the caller’s version”: explicit mismatch is not-found. One `resolve_version(name, version)` used by load, save, delete, `__delitem__`, `pop`, presign, and cache. `None` on delete/pop means **all versions** (Registry should match Store). `"latest"` is a read/delete alias, never stored. Batch save assigns versions sequentially in one plan. Missing explicit version always raises. Drop the process-local versions TTL, or key it by a backend generation/etag so another `Registry` on the same URI cannot serve a stale latest.

---

## 4. The cache is a second Registry, not a replica

**Bug.** Remote cache is another `_RegistryCore` on a local backend. Fill re-`save()`s the Python object (re-tar, new hash) instead of copying remote bytes+metadata. FULL verify compares hashes that need not match. Batch cached load omits `output_dir`. `commit_direct_upload` calls `clear_cache()`. `download` writes through `_core` (remote) and leaves the cache entry.

**Tests (integration; each minio + gcp unless noted)**

| ID | Test | Observed |
|---|---|---|
| C1 | `test_c1_cached_load_verify_full_uses_remote_artifact_hash` | **minio passed** (hashes matched for that Path). **gcp failed**: cache hash ≠ remote hash; logs show re-tar of `data.tar.gz` on cache write-back, then another re-serialize on FULL. |
| C3 | `test_c3_cached_batch_load_honors_output_dir_on_cache_hits` | Batch hit returned Path under `/var/folders/.../tmp.../a.txt`, not `output_dir`. `_load_batch_cached` does not forward `output_dir` on cache hits. |
| C4 | `test_c4_commit_direct_upload_does_not_wipe_unrelated_cache_entries` | After commit of a *different* name, unrelated cache entry gone. Log: `Cleared local cache.` |
| R9 | `test_r9_download_updates_or_invalidates_the_remote_cache` | Download wrote `2` to remote; `load(..., verify='none')` still returned `1` from cache. |

**Suggested fix.** Cache is a byte-for-byte replica: copy artifact directory + metadata; never rematerialize on fill. Cache key is `(name, concrete_version)` plus remote hash. One cached-load path so `output_dir` / verify apply to batch and single. Every remote mutation (`save`, `delete`, `download`, `commit_direct_upload`) invalidates or overwrites **only those keys**. No `clear_cache()` on a single commit.

C1 on MinIO passing does **not** disprove the design bug; GCS showed the re-serialize hash split. Prefer a test that asserts cache fill copies remote hash, not that gzip happened to be deterministic.

---

## 5. Types and materializers are inferred, then overwritten

**Bug.** `save(..., materializer=MyClass)` uses `type(MyClass)` → `builtins.type`. Opening a Registry re-registers defaults and clobbers a custom mapping for the same class. Shared `metadata` / `init_params` dicts are dropped in batch (`[None]*n`). Stored `init_params` are splatted into `materializer.load()`, not `__init__`. Builtins go through JSON, so nested tuples become lists.

**Tests**

| ID | Test | Observed |
|---|---|---|
| R1 | `test_save_accepts_materializer_class` | `TypeError: type() takes 1 or 3 arguments`. |
| R4 | `test_batch_save_broadcasts_shared_metadata_dict` | `KeyError: 'desc'`. |
| R4 | `test_batch_save_broadcasts_shared_init_params_dict` | Stored `init_params` `{}`. |
| R6 | `test_reopening_registry_does_not_clobber_custom_materializers` | Reopen restores `BuiltInMaterializer` over `custom.IntMaterializer`. |
| R10 | `test_init_params_round_trip_does_not_break_load` | `BuiltInMaterializer.load() got unexpected keyword argument 'custom_flag'`. |
| M1 | `test_nested_tuples_round_trip` | Inner tuple becomes a list. |
| M2 | `test_load_with_unimportable_class_still_returns_json_container` | **Passed.** |

**Suggested fix.** Materializer is an explicit class/import path or a table lookup on the object’s type *instance*, never `type(the_class)`. Defaults fill only missing class keys; never overwrite a stored custom. Broadcast a single metadata/init_params dict across a batch (copy per item). `init_params` construct the materializer; `load()` gets load kwargs only. For Python builtins, use a format that preserves tuples (or a dedicated tuple materializer).

---

## 6. The dict façade is a third API

**Bug.** `__contains__`, `__getitem__`, `__delitem__`, and `pop` do not share resolution, exceptions, or version policy.

**Tests**

| ID | Test | Observed |
|---|---|---|
| S5 | `test_contains_true_implies_getitem_succeeds` | See issue 2. |
| S6 | `test_missing_getitem_raises_keyerror` | `RegistryObjectNotFound`, not `KeyError`. |
| R7 / R8 | delitem tests | See issue 3. |
| — | Registry vs Store `pop` | Store already deletes all versions; Registry does not. |

**Suggested fix.** Either implement `MutableMapping` strictly (`KeyError`, same resolver as `load`/`delete`, `pop(name)` = all versions) or drop the dict pretence and keep only explicit methods. `name@version` strings must go through the same parser and `resolve_version` in every dunder.

---

## 7. “Exists” means “a metadata file we might smash”

**Bug.** Existence is a metadata document. Delete of a missing version can report success. Corrupt registry metadata is treated as empty and reinitialized.

**Tests**

| ID | Test | Observed |
|---|---|---|
| B4 | `test_delete_missing_explicit_version_raises` | No raise. |
| R3 | `test_unversioned_delete_of_missing_name_raises` | Silent success. |
| B5 | `test_corrupt_registry_metadata_does_not_silently_reinitialize` | Corrupt JSON: `Registry(...)` succeeds. |

**Suggested fix.** Existence = metadata fetch that parses. Unreadable metadata is a hard error (`RegistryCorruptError`), never silent reinit. Missing explicit delete targets raise (unless you explicitly document idempotent delete and change the tests). Do not write a fresh metadata file on open unless the URI is truly empty.

---

## Suggested order of work (if implementing)

1. **Opaque names + encoded metadata keys** (issue 1) — unblocks B1/B2/B3 and Store parse (S1).
2. **Single `resolve_version` + pop/delete policy** (issue 3) — unblocks R2/R3/R5/R7/R8/B4/C5 and Registry pop.
3. **Single Store resolver for read and write** (issue 2) — unblocks S2/S4/S5/S7 and presign.
4. **Cache as byte replica + per-key invalidation** (issue 4) — unblocks C1/C3/C4/R9.
5. **Materializer table + batch broadcast + init_params** (issue 5).
6. **Dict façade aligned or removed** (issue 6).
7. **Corrupt metadata hard-fail** (issue 7).

Keep diffs small and one intent per PR. Do not “fix” Store `pop` or M2. Prefer making the new `*BugHunt` tests pass over adding more tests unless a gap is real (C2 race, S2 control `None` vs not-found).

---

## Implementation notes for a fixer

- Public surface: `mindtrace/registry/mindtrace/registry/` — `core/registry.py`, `_registry_core.py`, `store.py`, `mount.py`; `backends/local|s3|gcp_registry_backend.py`.
- Cached `Registry`: `_core` is the **remote**, `_cache` is a local `_RegistryCore`. `download` uses `_core`; `commit_direct_upload` calls `clear_cache()`. `_load_batch_cached` skips `output_dir` on cache hits; `_load_single_cached` does not.
- Store unqualified mutation: `resolved_mount = mount or self.default_mount` in save/delete/presign; load searches mounts.
- Existing unit tests sometimes **assert the buggy behavior** (e.g. `_find_materializer(Class) == "builtins.type"`, `parse_key("nested/path")` unqualified). Changing production code may require updating those, not the BugHunt tests.
- Architecture: do not add new upward dependency edges; see `AGENTS.md` / `README.md`.

---

## Out of scope for this branch

- Production fixes.
- Committing unrelated refactors.
- Running the full integration suite beyond the two new files.
- AWS as a third backend param (MinIO is the S3 stand-in; same `S3RegistryBackend`).

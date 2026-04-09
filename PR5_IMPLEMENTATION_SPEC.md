# PR #5 Implementation Spec — Production Annotation Schemas

## Proposed Title

**[Datalake 5 of X]: Production Annotation Schemas**

---

## Objective

Introduce first-class annotation schemas to the V3 Datalake so that:

- annotation schemas are persisted as canonical entities
- `AnnotationSet` can declare a schema contract
- writes into schema-bound sets are validated on insertion
- invalid labels, kinds, geometry, and attributes are rejected with clear errors

This PR builds on PR #414's parent-only containment model and treats the annotation set as the primary schema / provenance boundary.

---

## Scope

### In scope

- Add `AnnotationSchema` and supporting schema types
- Add `annotation_schema_id` to `AnnotationSet`
- Add async + sync schema CRUD/list APIs
- Validate records in `add_annotation_records(...)` when destination set is schema-bound
- Add focused unit and integration coverage

### Out of scope

- Full schema-aware validation on `update_annotation_record(...)`
- Cross-set mutation consistency enforcement
- Ontology hierarchy / inheritance
- Rich user-defined schema DSLs
- Query/view DSL work
- Export/import or compatibility layers

---

## Core Design Decisions

### 1. Schema is set-bound

Schema identity belongs on `AnnotationSet`, not `AnnotationRecord`.

Rationale:
- `AnnotationSet` is already the grouping/provenance boundary
- `AnnotationRecord` is intentionally reusable across multiple sets after PR #414
- record-level schema identity would complicate reuse semantics too early

### 2. Validate on insertion into a set

PR #5 validates records when they are inserted into a schema-bound annotation set.

Primary enforcement point:
- `AsyncDatalake.add_annotation_records(annotation_set_id, annotations)`

Deferred:
- full validation of record updates across all referencing sets

### 3. Keep the schema model explicit and narrow

Do not build a generic meta-schema system in this PR.

Support a practical first-pass surface:
- classification
- detection (`bbox` only in first-pass tests/behavior)
- segmentation (`mask` only in first-pass tests/behavior)

Optional later:
- `rotated_bbox`
- `instance_mask`
- `keypoint`

---

## Proposed Data Model

## New types in `mindtrace/datalake/mindtrace/datalake/types.py`

### `AnnotationTaskType`

Use a literal/enum-like type:

- `classification`
- `detection`
- `segmentation`
- `keypoint`
- `other`

### `AnnotationLabelDefinition`

Fields:
- `name: str`
- `id: int | None = None`
- `display_name: str | None = None`
- `color: str | None = None`
- `metadata: dict[str, Any] = Field(default_factory=dict)`

Notes:
- keep label definitions lightweight
- do **not** add per-label attribute schemas in PR #5

### `AnnotationSchema`

Fields:
- `annotation_schema_id: str`
- `name: str`
- `version: str`
- `task_type: AnnotationTaskType`
- `allowed_annotation_kinds: list[Literal[...]]`
- `labels: list[AnnotationLabelDefinition]`
- `allow_scores: bool = False`
- `required_attributes: list[str] = Field(default_factory=list)`
- `optional_attributes: list[str] = Field(default_factory=list)`
- `allow_additional_attributes: bool = False`
- `metadata: dict[str, Any] = Field(default_factory=dict)`
- `created_at`
- `created_by`
- `updated_at`

Indexes:
- unique `annotation_schema_id`
- index on `task_type`
- compound index on `(name, version)`

### `AnnotationSet`

Add:
- `annotation_schema_id: str | None = None`

Do **not** add duplicate convenience fields in this PR such as:
- `schema_name`
- `schema_version`
- `task_type`

---

## API Changes

## Async API additions

Add to `AsyncDatalake`:

- `create_annotation_schema(...)`
- `get_annotation_schema(annotation_schema_id: str)`
- `get_annotation_schema_by_name_version(name: str, version: str)`
- `list_annotation_schemas(filters: dict[str, Any] | None = None)`
- `update_annotation_schema(annotation_schema_id: str, **changes)`
- `delete_annotation_schema(annotation_schema_id: str)`

### Async API updates

#### `create_annotation_set(...)`
Add parameter:
- `annotation_schema_id: str | None = None`

Behavior:
- if provided, verify the schema exists before insert

#### `add_annotation_records(...)`
Behavior:
- fetch destination annotation set
- if set has `annotation_schema_id`, fetch schema
- validate each record before insertion
- reject invalid records with explicit errors

#### `summary()`
Include schema count.

## Sync facade additions

Add matching wrappers in `mindtrace/datalake/mindtrace/datalake/datalake.py` for:
- create/get/list/update/delete schema
- get-by-name-version helper if desired

---

## Validation Rules

## Error type

Add a dedicated exception, e.g.:

- `AnnotationSchemaValidationError(ValueError)`

Use this for schema contract failures.

### Validation helpers in `AsyncDatalake`

Add private helpers:
- `_validate_annotation_record_against_schema(...)`
- `_validate_annotation_kind_for_schema(...)`
- `_validate_annotation_label_for_schema(...)`
- `_validate_annotation_geometry_for_schema(...)`
- `_validate_annotation_attributes_for_schema(...)`

### Label validation

Rules:
- `annotation.label` must exist in `schema.labels`
- if `annotation.label_id` is provided and matching schema label id exists, it must match

### Kind validation

Rules:
- `annotation.kind` must be in `schema.allowed_annotation_kinds`

Examples:
- classification schema -> `['classification']`
- detection schema -> `['bbox']`
- segmentation schema -> `['mask']`

### Score validation

Rules:
- if `annotation.score is not None` and `schema.allow_scores is False`, reject

### Attribute validation

Rules:
- every key in `required_attributes` must be present
- keys must be drawn from `required_attributes ∪ optional_attributes` unless `allow_additional_attributes=True`

### Geometry validation by task family

#### Classification
Expected:
- kind `classification`
- geometry empty / absent

Reject if:
- geometry is non-empty

#### Detection
Expected first-pass:
- kind `bbox`
- geometry includes `x`, `y`, `width`, `height`

Reject if:
- required bbox fields are missing
- kind is not allowed

#### Segmentation
Expected first-pass:
- kind `mask`
- geometry is non-empty
- geometry includes at least one of:
  - `storage_ref`
  - `mask_asset_id`
  - `encoding`

Reject if:
- geometry is empty
- none of the minimal mask markers exist

---

## Behavior explicitly deferred

### Record mutation semantics

Because records may belong to multiple schema-bound sets, do **not** fully solve schema-aware mutation consistency in this PR.

For PR #5:
- insertion into a schema-bound set is validated
- direct record updates are left as existing generic behavior
- PR description should call this out as a deliberate scope boundary

---

## File-by-file Change Plan

### `mindtrace/datalake/mindtrace/datalake/types.py`
- add `AnnotationTaskType`
- add `AnnotationLabelDefinition`
- add `AnnotationSchema`
- add `annotation_schema_id` to `AnnotationSet`
- export / string representations / indexes as needed

### `mindtrace/datalake/mindtrace/datalake/__init__.py`
- export new schema types

### `mindtrace/datalake/mindtrace/datalake/async_datalake.py`
- initialize annotation schema ODM
- add schema CRUD/list methods
- add schema lookup by name/version
- add validation exception and helper methods
- update `create_annotation_set(...)`
- update `add_annotation_records(...)`
- update `summary()`

### `mindtrace/datalake/mindtrace/datalake/datalake.py`
- add sync wrappers for schema methods
- pass through updated `create_annotation_set(...)`

### Tests
- `tests/unit/mindtrace/datalake/test_datalake_types.py`
- `tests/unit/mindtrace/datalake/test_async_datalake.py`
- `tests/unit/mindtrace/datalake/test_datalake.py`
- `tests/integration/mindtrace/datalake/test_async_datalake_integration.py`
- `tests/integration/mindtrace/datalake/test_datalake_integration.py`
- `tests/integration/mindtrace/datalake/test_datalake_types_integration.py`

---

## Test Plan

## Unit

### Types
- schema model creation/defaults
- label definition creation/defaults
- annotation set schema reference

### Async Datalake
- create/get/list/update/delete schema
- create annotation set with valid schema ref
- reject annotation set creation with unknown schema ref
- valid classification insert succeeds
- invalid classification label fails
- invalid bbox geometry fails
- valid bbox insert succeeds
- invalid score rejected when schema disallows scores
- attribute allowlist / required checks behave correctly

### Sync facade
- schema CRUD wrappers
- create schema-bound annotation set
- validated insertion through sync facade

## Integration

Keep coverage compact and representative:

1. schema CRUD roundtrip
2. classification success flow
3. invalid label rejection
4. bbox geometry rejection
5. bbox success flow
6. mask success or minimal validation flow

---

## Implementation Checklist

- [ ] Add schema types to `types.py`
- [ ] Export schema types from `__init__.py`
- [ ] Add schema ODM initialization to `AsyncDatalake`
- [ ] Add async schema CRUD/list methods
- [ ] Add sync schema wrappers
- [ ] Add `annotation_schema_id` to `AnnotationSet`
- [ ] Validate schema existence in `create_annotation_set(...)`
- [ ] Add schema validation error type
- [ ] Add validation helper methods
- [ ] Enforce validation in `add_annotation_records(...)`
- [ ] Update summary to include schema counts
- [ ] Add/adjust unit tests
- [ ] Add/adjust integration tests
- [ ] Write focused PR description noting deferred mutation semantics

---

## Recommended PR Narrative

This PR introduces first-class production annotation schemas to the V3 Datalake. Annotation sets can now declare a schema contract, and annotation records are validated against that contract when inserted into schema-bound sets. The initial implementation intentionally focuses on a narrow practical surface — classification, bbox detection, and mask segmentation — while deferring more complex cross-set mutation semantics and richer ontology features to later PRs.

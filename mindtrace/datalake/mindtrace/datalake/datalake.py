from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any, TypeVar

from mindtrace.core import Mindtrace
from mindtrace.database import MongoMindtraceODM
from mindtrace.database.core.exceptions import DocumentNotFoundError
from mindtrace.datalake.types import (
    AnnotationRecord,
    AnnotationSet,
    AnnotationSource,
    Asset,
    DatasetVersion,
    Datum,
    ResolvedDatasetVersion,
    ResolvedDatum,
    StorageRef,
    SubjectRef,
)
from mindtrace.registry import Mount, Registry, Store


DocumentT = TypeVar("DocumentT")


class Datalake(Mindtrace):
    """V3 datalake facade for canonical records over Store-backed payloads."""

    def __init__(
        self,
        mongo_db_uri: str,
        mongo_db_name: str,
        *,
        store: Store | None = None,
        mounts: list[Mount] | None = None,
        default_mount: str | None = None,
    ) -> None:
        super().__init__()
        self.mongo_db_uri = mongo_db_uri
        self.mongo_db_name = mongo_db_name

        if store is not None and mounts is not None:
            raise ValueError("Provide either store or mounts, not both")

        if store is not None:
            self.store = store
        elif mounts is not None:
            self.store = Store.from_mounts(mounts, default_mount=default_mount)
        else:
            self.store = Store(default_mount=default_mount or "temp")

        self.asset_database = MongoMindtraceODM(model_cls=Asset, db_name=mongo_db_name, db_uri=mongo_db_uri)
        self.annotation_record_database = MongoMindtraceODM(
            model_cls=AnnotationRecord,
            db_name=mongo_db_name,
            db_uri=mongo_db_uri,
        )
        self.annotation_set_database = MongoMindtraceODM(
            model_cls=AnnotationSet,
            db_name=mongo_db_name,
            db_uri=mongo_db_uri,
        )
        self.datum_database = MongoMindtraceODM(model_cls=Datum, db_name=mongo_db_name, db_uri=mongo_db_uri)
        self.dataset_version_database = MongoMindtraceODM(
            model_cls=DatasetVersion,
            db_name=mongo_db_name,
            db_uri=mongo_db_uri,
        )

    async def initialize(self) -> None:
        await self.asset_database.initialize()
        await self.annotation_record_database.initialize()
        await self.annotation_set_database.initialize()
        await self.datum_database.initialize()
        await self.dataset_version_database.initialize()

    @classmethod
    async def create(
        cls,
        mongo_db_uri: str,
        mongo_db_name: str,
        *,
        store: Store | None = None,
        mounts: list[Mount] | None = None,
        default_mount: str | None = None,
    ) -> "Datalake":
        datalake = cls(
            mongo_db_uri=mongo_db_uri,
            mongo_db_name=mongo_db_name,
            store=store,
            mounts=mounts,
            default_mount=default_mount,
        )
        await datalake.initialize()
        return datalake

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _normalize_storage_ref(storage_ref: StorageRef) -> StorageRef:
        return StorageRef(
            mount=storage_ref.mount,
            name=storage_ref.name,
            version=storage_ref.version,
        )

    @staticmethod
    def _build_document(model_cls: type[DocumentT], **data: Any) -> DocumentT:
        """Construct Beanie documents without requiring collection initialization."""
        return model_cls.model_construct(**data)

    async def get_health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "database": self.mongo_db_name,
            "default_mount": self.store.default_mount,
        }

    def get_mounts(self) -> dict[str, Any]:
        mount_info = self.store.list_mount_info()
        mounts = [
            {
                "name": name,
                **info,
            }
            for name, info in mount_info.items()
        ]
        return {
            "default_mount": self.store.default_mount,
            "mounts": mounts,
        }

    async def put_object(
        self,
        *,
        name: str,
        obj: Any,
        mount: str | None = None,
        version: str | None = None,
        metadata: dict[str, Any] | None = None,
        on_conflict: str | None = None,
    ) -> StorageRef:
        target_mount = mount or self.store.default_mount
        key = self.store.build_key(target_mount, name, version)
        saved_version = self.store.save(key, obj, version=version, metadata=metadata, on_conflict=on_conflict)
        resolved_version = saved_version if isinstance(saved_version, str) else version or "latest"
        return StorageRef(mount=target_mount, name=name, version=resolved_version)

    async def get_object(self, storage_ref: StorageRef, **kwargs) -> Any:
        storage_ref = self._normalize_storage_ref(storage_ref)
        key = self.store.build_key(storage_ref.mount, storage_ref.name, storage_ref.version)
        return self.store.load(key, version=storage_ref.version, **kwargs)

    async def head_object(self, storage_ref: StorageRef) -> dict[str, Any]:
        storage_ref = self._normalize_storage_ref(storage_ref)
        key = self.store.build_key(storage_ref.mount, storage_ref.name, storage_ref.version)
        return self.store.info(key, version=storage_ref.version)

    async def copy_object(
        self,
        source: StorageRef,
        *,
        target_mount: str,
        target_name: str,
        target_version: str | None = None,
    ) -> StorageRef:
        source = self._normalize_storage_ref(source)
        source_key = self.store.build_key(source.mount, source.name, source.version)
        target_key = self.store.build_key(target_mount, target_name, target_version)
        saved_version = self.store.copy(
            source_key,
            target=target_key,
            source_version=source.version or "latest",
            target_version=target_version,
        )
        return StorageRef(mount=target_mount, name=target_name, version=saved_version)

    async def create_asset(
        self,
        *,
        kind: str,
        media_type: str,
        storage_ref: StorageRef,
        checksum: str | None = None,
        size_bytes: int | None = None,
        subject: SubjectRef | None = None,
        metadata: dict[str, Any] | None = None,
        created_by: str | None = None,
    ) -> Asset:
        asset = self._build_document(
            Asset,
            kind=kind,
            media_type=media_type,
            storage_ref=self._normalize_storage_ref(storage_ref),
            checksum=checksum,
            size_bytes=size_bytes,
            subject=subject,
            metadata=metadata or {},
            created_by=created_by,
            updated_at=self._utc_now(),
        )
        return await self.asset_database.insert(asset)

    async def get_asset(self, asset_id: str) -> Asset:
        results = await self.asset_database.find({"asset_id": asset_id})
        if not results:
            raise DocumentNotFoundError(f"Asset with asset_id {asset_id} not found")
        return results[0]

    async def list_assets(self, filters: dict[str, Any] | None = None) -> list[Asset]:
        return await self.asset_database.find(filters or {})

    async def update_asset_metadata(self, asset_id: str, metadata: dict[str, Any]) -> Asset:
        asset = await self.get_asset(asset_id)
        asset.metadata = metadata
        asset.updated_at = self._utc_now()
        return await self.asset_database.update(asset)

    async def delete_asset(self, asset_id: str) -> None:
        asset = await self.get_asset(asset_id)
        await self.asset_database.delete(asset.id)

    async def create_annotation_set(
        self,
        *,
        name: str,
        purpose: str,
        source_type: str,
        status: str = "draft",
        metadata: dict[str, Any] | None = None,
        created_by: str | None = None,
        datum_id: str | None = None,
    ) -> AnnotationSet:
        annotation_set = self._build_document(
            AnnotationSet,
            datum_id=datum_id,
            name=name,
            purpose=purpose,
            source_type=source_type,
            status=status,
            metadata=metadata or {},
            created_by=created_by,
            updated_at=self._utc_now(),
        )
        inserted = await self.annotation_set_database.insert(annotation_set)
        if datum_id is not None:
            datum = await self.get_datum(datum_id)
            datum.annotation_set_ids.append(inserted.annotation_set_id)
            datum.updated_at = self._utc_now()
            await self.datum_database.update(datum)
        return inserted

    async def get_annotation_set(self, annotation_set_id: str) -> AnnotationSet:
        results = await self.annotation_set_database.find({"annotation_set_id": annotation_set_id})
        if not results:
            raise DocumentNotFoundError(f"AnnotationSet with annotation_set_id {annotation_set_id} not found")
        return results[0]

    async def list_annotation_sets(self, filters: dict[str, Any] | None = None) -> list[AnnotationSet]:
        return await self.annotation_set_database.find(filters or {})

    async def add_annotation_records(
        self,
        annotation_set_id: str,
        annotations: Iterable[AnnotationRecord | dict[str, Any]],
    ) -> list[AnnotationRecord]:
        annotation_set = await self.get_annotation_set(annotation_set_id)
        inserted_records: list[AnnotationRecord] = []
        for annotation in annotations:
            if isinstance(annotation, AnnotationRecord):
                record = annotation
                record.annotation_set_id = annotation_set_id
                record.updated_at = self._utc_now()
            else:
                source = annotation.get("source")
                if isinstance(source, dict):
                    source = AnnotationSource(**source)
                record = self._build_document(
                    AnnotationRecord,
                    annotation_set_id=annotation_set_id,
                    subject=annotation.get("subject"),
                    kind=annotation["kind"],
                    label=annotation["label"],
                    label_id=annotation.get("label_id"),
                    score=annotation.get("score"),
                    source=source,
                    geometry=annotation.get("geometry", {}),
                    attributes=annotation.get("attributes", {}),
                    updated_at=self._utc_now(),
                )
            inserted = await self.annotation_record_database.insert(record)
            inserted_records.append(inserted)
            annotation_set.annotation_record_ids.append(inserted.annotation_id)
        annotation_set.updated_at = self._utc_now()
        await self.annotation_set_database.update(annotation_set)
        return inserted_records

    async def get_annotation_record(self, annotation_id: str) -> AnnotationRecord:
        results = await self.annotation_record_database.find({"annotation_id": annotation_id})
        if not results:
            raise DocumentNotFoundError(f"AnnotationRecord with annotation_id {annotation_id} not found")
        return results[0]

    async def list_annotation_records(self, filters: dict[str, Any] | None = None) -> list[AnnotationRecord]:
        return await self.annotation_record_database.find(filters or {})

    async def update_annotation_record(self, annotation_id: str, **changes: Any) -> AnnotationRecord:
        record = await self.get_annotation_record(annotation_id)
        for key, value in changes.items():
            if key == "source" and isinstance(value, dict):
                value = AnnotationSource(**value)
            setattr(record, key, value)
        record.updated_at = self._utc_now()
        return await self.annotation_record_database.update(record)

    async def delete_annotation_record(self, annotation_id: str) -> None:
        record = await self.get_annotation_record(annotation_id)
        if record.annotation_set_id is not None:
            annotation_set = await self.get_annotation_set(record.annotation_set_id)
            annotation_set.annotation_record_ids = [
                existing_id for existing_id in annotation_set.annotation_record_ids if existing_id != annotation_id
            ]
            annotation_set.updated_at = self._utc_now()
            await self.annotation_set_database.update(annotation_set)
        await self.annotation_record_database.delete(record.id)

    async def create_datum(
        self,
        *,
        asset_refs: dict[str, str],
        split: str | None = None,
        metadata: dict[str, Any] | None = None,
        annotation_set_ids: list[str] | None = None,
    ) -> Datum:
        datum = self._build_document(
            Datum,
            split=split,
            asset_refs=asset_refs,
            metadata=metadata or {},
            annotation_set_ids=annotation_set_ids or [],
            updated_at=self._utc_now(),
        )
        return await self.datum_database.insert(datum)

    async def get_datum(self, datum_id: str) -> Datum:
        results = await self.datum_database.find({"datum_id": datum_id})
        if not results:
            raise DocumentNotFoundError(f"Datum with datum_id {datum_id} not found")
        return results[0]

    async def list_datums(self, filters: dict[str, Any] | None = None) -> list[Datum]:
        return await self.datum_database.find(filters or {})

    async def update_datum(self, datum_id: str, **changes: Any) -> Datum:
        datum = await self.get_datum(datum_id)
        for key, value in changes.items():
            setattr(datum, key, value)
        datum.updated_at = self._utc_now()
        return await self.datum_database.update(datum)

    async def create_dataset_version(
        self,
        *,
        dataset_name: str,
        version: str,
        manifest: list[str],
        description: str | None = None,
        source_dataset_version_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        created_by: str | None = None,
    ) -> DatasetVersion:
        existing = await self.dataset_version_database.find({"dataset_name": dataset_name, "version": version})
        if existing:
            raise ValueError(f"Dataset version already exists: {dataset_name}@{version}")
        dataset_version = self._build_document(
            DatasetVersion,
            dataset_name=dataset_name,
            version=version,
            description=description,
            manifest=manifest,
            source_dataset_version_id=source_dataset_version_id,
            metadata=metadata or {},
            created_by=created_by,
        )
        return await self.dataset_version_database.insert(dataset_version)

    async def get_dataset_version(self, dataset_name: str, version: str) -> DatasetVersion:
        results = await self.dataset_version_database.find({"dataset_name": dataset_name, "version": version})
        if not results:
            raise DocumentNotFoundError(f"DatasetVersion {dataset_name}@{version} not found")
        return results[0]

    async def list_dataset_versions(
        self,
        dataset_name: str | None = None,
        filters: dict[str, Any] | None = None,
    ) -> list[DatasetVersion]:
        query = dict(filters or {})
        if dataset_name is not None:
            query["dataset_name"] = dataset_name
        return await self.dataset_version_database.find(query)

    async def resolve_datum(self, datum_id: str) -> ResolvedDatum:
        datum = await self.get_datum(datum_id)
        assets: dict[str, Asset] = {}
        for role, asset_id in datum.asset_refs.items():
            assets[role] = await self.get_asset(asset_id)

        annotation_sets: list[AnnotationSet] = []
        annotation_records: dict[str, list[AnnotationRecord]] = {}
        for annotation_set_id in datum.annotation_set_ids:
            annotation_set = await self.get_annotation_set(annotation_set_id)
            annotation_sets.append(annotation_set)
            records: list[AnnotationRecord] = []
            for annotation_id in annotation_set.annotation_record_ids:
                records.append(await self.get_annotation_record(annotation_id))
            annotation_records[annotation_set.annotation_set_id] = records

        return ResolvedDatum(
            datum=datum,
            assets=assets,
            annotation_sets=annotation_sets,
            annotation_records=annotation_records,
        )

    async def resolve_dataset_version(self, dataset_name: str, version: str) -> ResolvedDatasetVersion:
        dataset_version = await self.get_dataset_version(dataset_name, version)
        datums = [await self.resolve_datum(datum_id) for datum_id in dataset_version.manifest]
        return ResolvedDatasetVersion(dataset_version=dataset_version, datums=datums)

    async def create_asset_from_object(
        self,
        *,
        name: str,
        obj: Any,
        kind: str,
        media_type: str,
        mount: str | None = None,
        version: str | None = None,
        object_metadata: dict[str, Any] | None = None,
        asset_metadata: dict[str, Any] | None = None,
        checksum: str | None = None,
        size_bytes: int | None = None,
        subject: SubjectRef | None = None,
        created_by: str | None = None,
        on_conflict: str | None = None,
    ) -> Asset:
        storage_ref = await self.put_object(
            name=name,
            obj=obj,
            mount=mount,
            version=version,
            metadata=object_metadata,
            on_conflict=on_conflict,
        )
        return await self.create_asset(
            kind=kind,
            media_type=media_type,
            storage_ref=storage_ref,
            checksum=checksum,
            size_bytes=size_bytes,
            subject=subject,
            metadata=asset_metadata,
            created_by=created_by,
        )

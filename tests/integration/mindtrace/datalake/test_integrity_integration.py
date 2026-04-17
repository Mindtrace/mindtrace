from pathlib import Path
from uuid import uuid4

import pytest

from mindtrace.database.core.exceptions import DocumentNotFoundError
from mindtrace.datalake import AsyncDatalake


async def _create_image_asset(datalake: AsyncDatalake, *, name: str):
    image_bytes = Path("tests/resources/hopper.png").read_bytes()
    storage_ref = await datalake.put_object(name=name, obj=image_bytes, metadata={"integration": "integrity"})
    return await datalake.create_asset(
        kind="image",
        media_type="image/png",
        storage_ref=storage_ref,
        size_bytes=len(image_bytes),
        metadata={"integration": "integrity", "name": name},
        created_by="pytest-integrity",
    )


@pytest.mark.asyncio
async def test_create_datum_rejects_missing_asset_refs(async_datalake: AsyncDatalake):
    assert await async_datalake.list_datums() == []

    with pytest.raises(DocumentNotFoundError):
        await async_datalake.create_datum(asset_refs={"image": "missing_asset"}, split="train")

    assert await async_datalake.list_datums() == []


@pytest.mark.asyncio
async def test_update_datum_rejects_missing_asset_refs(async_datalake: AsyncDatalake):
    asset = await _create_image_asset(async_datalake, name=f"integrity/update/{uuid4().hex}.png")
    datum = await async_datalake.create_datum(
        asset_refs={"image": asset.asset_id},
        split="train",
        metadata={"integration": "integrity"},
    )

    with pytest.raises(DocumentNotFoundError):
        await async_datalake.update_datum(datum.datum_id, asset_refs={"image": "missing_asset"})

    refreshed = await async_datalake.get_datum(datum.datum_id)
    assert refreshed.asset_refs == {"image": asset.asset_id}


@pytest.mark.asyncio
async def test_delete_asset_rejects_when_still_referenced_by_datum(async_datalake: AsyncDatalake):
    asset = await _create_image_asset(async_datalake, name=f"integrity/delete/{uuid4().hex}.png")
    datum = await async_datalake.create_datum(
        asset_refs={"image": asset.asset_id},
        split="train",
        metadata={"integration": "integrity"},
    )

    with pytest.raises(ValueError, match="still referenced"):
        await async_datalake.delete_asset(asset.asset_id)

    refreshed_asset = await async_datalake.get_asset(asset.asset_id)
    refreshed_datum = await async_datalake.get_datum(datum.datum_id)
    assert refreshed_asset.asset_id == asset.asset_id
    assert refreshed_datum.asset_refs["image"] == asset.asset_id


@pytest.mark.asyncio
async def test_create_annotation_set_with_missing_datum_is_atomic(async_datalake: AsyncDatalake):
    assert await async_datalake.list_annotation_sets() == []

    with pytest.raises(DocumentNotFoundError):
        await async_datalake.create_annotation_set(
            name="orphan-guard",
            purpose="ground_truth",
            source_type="human",
            datum_id="missing_datum",
        )

    assert await async_datalake.list_annotation_sets() == []


@pytest.mark.asyncio
async def test_create_annotation_set_links_to_datum_exactly_once(async_datalake: AsyncDatalake):
    asset = await _create_image_asset(async_datalake, name=f"integrity/annotation-set/{uuid4().hex}.png")
    datum = await async_datalake.create_datum(
        asset_refs={"image": asset.asset_id},
        split="train",
        metadata={"integration": "integrity"},
    )

    annotation_set = await async_datalake.create_annotation_set(
        name="linked-set",
        purpose="ground_truth",
        source_type="human",
        datum_id=datum.datum_id,
        metadata={"integration": "integrity"},
    )

    refreshed = await async_datalake.get_datum(datum.datum_id)
    fetched_set = await async_datalake.get_annotation_set(annotation_set.annotation_set_id)

    assert refreshed.annotation_set_ids.count(annotation_set.annotation_set_id) == 1
    assert fetched_set.annotation_set_id == annotation_set.annotation_set_id


@pytest.mark.asyncio
async def test_delete_collection_cascades_collection_items(async_datalake: AsyncDatalake):
    asset = await _create_image_asset(async_datalake, name=f"integrity/collection-orphan/{uuid4().hex}.png")
    collection = await async_datalake.create_collection(
        name=f"integrity-collection-{uuid4().hex[:8]}",
        metadata={"integration": "integrity"},
        created_by="pytest-integrity",
    )
    collection_item = await async_datalake.create_collection_item(
        collection_id=collection.collection_id,
        asset_id=asset.asset_id,
        split="train",
        metadata={"integration": "integrity"},
        added_by="pytest-integrity",
    )

    await async_datalake.delete_collection(collection.collection_id)

    with pytest.raises(DocumentNotFoundError, match="Collection with collection_id"):
        await async_datalake.get_collection(collection.collection_id)

    with pytest.raises(DocumentNotFoundError, match="CollectionItem with collection_item_id"):
        await async_datalake.get_collection_item(collection_item.collection_item_id)

    assert await async_datalake.list_collection_items({"collection_id": collection.collection_id}) == []


@pytest.mark.asyncio
async def test_delete_asset_rejects_when_still_referenced_by_collection_item(async_datalake: AsyncDatalake):
    asset = await _create_image_asset(async_datalake, name=f"integrity/asset-orphan/{uuid4().hex}.png")
    collection = await async_datalake.create_collection(
        name=f"integrity-collection-{uuid4().hex[:8]}",
        metadata={"integration": "integrity"},
        created_by="pytest-integrity",
    )
    collection_item = await async_datalake.create_collection_item(
        collection_id=collection.collection_id,
        asset_id=asset.asset_id,
        split="train",
        metadata={"integration": "integrity"},
        added_by="pytest-integrity",
    )

    with pytest.raises(ValueError, match="still referenced"):
        await async_datalake.delete_asset(asset.asset_id)

    refreshed_asset = await async_datalake.get_asset(asset.asset_id)
    refreshed_item = await async_datalake.get_collection_item(collection_item.collection_item_id)
    assert refreshed_asset.asset_id == asset.asset_id
    assert refreshed_item.asset_id == asset.asset_id


@pytest.mark.asyncio
async def test_create_datum_rejects_missing_annotation_set_ids(async_datalake: AsyncDatalake):
    asset = await _create_image_asset(async_datalake, name=f"integrity/missing-ann-set-create/{uuid4().hex}.png")

    assert await async_datalake.list_datums() == []

    with pytest.raises(DocumentNotFoundError, match="AnnotationSet with annotation_set_id"):
        await async_datalake.create_datum(
            asset_refs={"image": asset.asset_id},
            split="train",
            metadata={"integration": "integrity"},
            annotation_set_ids=["missing_annotation_set"],
        )

    assert await async_datalake.list_datums() == []


@pytest.mark.asyncio
async def test_update_datum_rejects_missing_annotation_set_ids(async_datalake: AsyncDatalake):
    asset = await _create_image_asset(async_datalake, name=f"integrity/missing-ann-set-update/{uuid4().hex}.png")
    datum = await async_datalake.create_datum(
        asset_refs={"image": asset.asset_id},
        split="train",
        metadata={"integration": "integrity"},
    )

    with pytest.raises(DocumentNotFoundError, match="AnnotationSet with annotation_set_id"):
        await async_datalake.update_datum(datum.datum_id, annotation_set_ids=["missing_annotation_set"])

    persisted = await async_datalake.get_datum(datum.datum_id)
    assert persisted.annotation_set_ids == []


@pytest.mark.asyncio
async def test_create_dataset_version_rejects_missing_manifest_datum_ids(async_datalake: AsyncDatalake):
    dataset_name = f"integrity-missing-datum-{uuid4().hex[:10]}"

    with pytest.raises(DocumentNotFoundError, match="Datum with datum_id missing_datum not found"):
        await async_datalake.create_dataset_version(
            dataset_name=dataset_name,
            version="1.0.0",
            manifest=["missing_datum"],
            metadata={"integration": "integrity"},
            created_by="pytest-integrity",
        )

    assert await async_datalake.list_dataset_versions(dataset_name=dataset_name) == []


@pytest.mark.asyncio
async def test_create_dataset_version_rejects_duplicate_manifest_datum_ids(async_datalake: AsyncDatalake):
    asset = await _create_image_asset(async_datalake, name=f"integrity/duplicate-manifest/{uuid4().hex}.png")
    datum = await async_datalake.create_datum(
        asset_refs={"image": asset.asset_id},
        split="train",
        metadata={"integration": "integrity"},
    )
    dataset_name = f"integrity-duplicate-manifest-{uuid4().hex[:10]}"

    with pytest.raises(ValueError):
        await async_datalake.create_dataset_version(
            dataset_name=dataset_name,
            version="1.0.0",
            manifest=[datum.datum_id, datum.datum_id],
            metadata={"integration": "integrity"},
            created_by="pytest-integrity",
        )

    assert await async_datalake.list_dataset_versions(dataset_name=dataset_name) == []


@pytest.mark.asyncio
async def test_create_datum_rejects_blank_asset_ref(async_datalake: AsyncDatalake):
    assert await async_datalake.list_datums() == []

    with pytest.raises(ValueError, match="non-empty"):
        await async_datalake.create_datum(
            asset_refs={"image": ""},
            split="train",
            metadata={"integration": "integrity"},
        )

    assert await async_datalake.list_datums() == []


@pytest.mark.asyncio
async def test_update_datum_rejects_blank_asset_ref(async_datalake: AsyncDatalake):
    asset = await _create_image_asset(async_datalake, name=f"integrity/blank-asset-ref-update/{uuid4().hex}.png")
    datum = await async_datalake.create_datum(
        asset_refs={"image": asset.asset_id},
        split="train",
        metadata={"integration": "integrity"},
    )

    with pytest.raises(ValueError, match="non-empty"):
        await async_datalake.update_datum(datum.datum_id, asset_refs={"image": "   "})

    persisted = await async_datalake.get_datum(datum.datum_id)
    assert persisted.asset_refs == {"image": asset.asset_id}

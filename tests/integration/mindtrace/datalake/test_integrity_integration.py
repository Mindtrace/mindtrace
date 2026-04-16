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

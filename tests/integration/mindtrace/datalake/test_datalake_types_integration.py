from unittest.mock import patch

from beanie.exceptions import CollectionWasNotInitialized

from mindtrace.datalake.types import (
    AnnotationRecord,
    AnnotationSet,
    AnnotationSource,
    Asset,
    AssetRetention,
    Collection,
    CollectionItem,
    DatasetVersion,
    Datum,
    ResolvedCollectionItem,
    ResolvedDatasetVersion,
    ResolvedDatum,
    StorageRef,
    SubjectRef,
)


def test_types_string_representations():
    subject = SubjectRef(kind="asset", id="asset_1")
    storage_ref = StorageRef(mount="local", name="hopper.png", version="1.0.0")
    source = AnnotationSource(type="machine", name="detector", version="1.0.0")

    asset = Asset(kind="image", media_type="image/png", storage_ref=storage_ref, subject=subject)
    record = AnnotationRecord(kind="bbox", label="hopper", source=source, geometry={})
    annotation_set = AnnotationSet(name="ground-truth", purpose="ground_truth", source_type="human")
    collection = Collection(name="demo-collection")
    collection_item = CollectionItem(collection_id="collection_1", asset_id=asset.asset_id)
    asset_retention = AssetRetention(asset_id=asset.asset_id, owner_type="manual_pin", owner_id="owner_1")
    datum = Datum(asset_refs={"image": asset.asset_id}, split="train")
    dataset_version = DatasetVersion(dataset_name="demo", version="0.1.0", manifest=[datum.datum_id])
    resolved_collection_item = ResolvedCollectionItem(
        collection_item=collection_item,
        collection=collection,
        asset=asset,
    )
    resolved_datum = ResolvedDatum(
        datum=datum,
        assets={"image": asset},
        annotation_sets=[annotation_set],
        annotation_records={annotation_set.annotation_set_id: [record]},
    )
    resolved_dataset = ResolvedDatasetVersion(dataset_version=dataset_version, datums=[resolved_datum])

    assert str(subject) == "SubjectRef(kind=asset, id=asset_1)"
    assert str(storage_ref) == f"StorageRef({storage_ref.qualified_key})"
    assert str(source) == "AnnotationSource(type=machine, name=detector, version=1.0.0)"
    assert "Asset(asset_id=" in str(asset)
    assert "AnnotationRecord(annotation_id=" in str(record)
    assert "AnnotationSet(annotation_set_id=" in str(annotation_set)
    assert "Collection(collection_id=" in str(collection)
    assert "CollectionItem(collection_item_id=" in str(collection_item)
    assert "AssetRetention(asset_retention_id=" in str(asset_retention)
    assert "Datum(datum_id=" in str(datum)
    assert "DatasetVersion(dataset=demo, version=0.1.0, datums=1)" == str(dataset_version)
    assert "ResolvedCollectionItem(collection_item_id=" in str(resolved_collection_item)
    assert "ResolvedDatum(datum_id=" in str(resolved_datum)
    assert "ResolvedDatasetVersion(dataset=demo, version=0.1.0, datums=1)" == str(resolved_dataset)


def test_datalake_document_falls_back_to_pydantic_init_when_collection_is_uninitialized():
    with patch("mindtrace.datalake.types.MindtraceDocument.__init__", side_effect=CollectionWasNotInitialized()):
        asset = Asset(
            kind="image",
            media_type="image/png",
            storage_ref=StorageRef(mount="local", name="fallback.png"),
        )

    assert asset.kind == "image"
    assert asset.media_type == "image/png"
    assert asset.storage_ref.name == "fallback.png"

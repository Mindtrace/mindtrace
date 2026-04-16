from mindtrace.datalake.types import (
    AnnotationLabelDefinition,
    AnnotationRecord,
    AnnotationSchema,
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


def test_storage_ref_builds_qualified_key():
    ref = StorageRef(mount="nas", name="images/cat.jpg", version="v1")

    assert ref.qualified_key == "nas/images/cat.jpg@v1"
    assert str(ref) == "StorageRef(nas/images/cat.jpg@v1)"


def test_subject_ref_accepts_asset_and_annotation_kinds():
    asset_subject = SubjectRef(kind="asset", id="asset_123")
    annotation_subject = SubjectRef(kind="annotation", id="annotation_123")

    assert asset_subject.kind == "asset"
    assert annotation_subject.kind == "annotation"
    assert str(asset_subject) == "SubjectRef(kind=asset, id=asset_123)"


def test_annotation_source_defaults_metadata():
    source = AnnotationSource(type="machine", name="detector", version="1.0.0")

    assert source.metadata == {}
    assert str(source) == "AnnotationSource(type=machine, name=detector, version=1.0.0)"


def test_main_type_str_methods_are_readable():
    storage_ref = StorageRef(mount="temp", name="hopper.png")
    asset = Asset(kind="image", media_type="image/png", storage_ref=storage_ref)
    collection = Collection(name="demo-collection")
    collection_item = CollectionItem(collection_id=collection.collection_id, asset_id=asset.asset_id)
    asset_retention = AssetRetention(asset_id=asset.asset_id, owner_type="manual_pin", owner_id="owner_1")
    record = AnnotationRecord(
        kind="bbox",
        label="dent",
        source={"type": "human", "name": "review-ui"},
        geometry={},
        metadata={"origin": "unit"},
    )
    annotation_set = AnnotationSet(name="gt", purpose="ground_truth", source_type="human")
    datum = Datum(asset_refs={"image": asset.asset_id}, split="train")
    dataset_version = DatasetVersion(dataset_name="demo", version="0.1.0", manifest=[datum.datum_id])
    resolved_collection_item = ResolvedCollectionItem(
        collection_item=collection_item,
        collection=collection,
        asset=asset,
    )
    resolved_datum = ResolvedDatum(datum=datum, assets={"image": asset}, annotation_sets=[annotation_set])
    resolved_dataset = ResolvedDatasetVersion(dataset_version=dataset_version, datums=[resolved_datum])

    assert "Asset(asset_id=" in str(asset)
    assert "Collection(collection_id=" in str(collection)
    assert "CollectionItem(collection_item_id=" in str(collection_item)
    assert "AssetRetention(asset_retention_id=" in str(asset_retention)
    assert record.metadata == {"origin": "unit"}
    assert "AnnotationRecord(annotation_id=" in str(record)
    assert "AnnotationSet(annotation_set_id=" in str(annotation_set)
    assert "Datum(datum_id=" in str(datum)
    assert "ResolvedCollectionItem(collection_item_id=" in str(resolved_collection_item)
    assert str(dataset_version) == "DatasetVersion(dataset=demo, version=0.1.0, datums=1)"
    assert str(resolved_datum) == f"ResolvedDatum(datum_id={datum.datum_id}, assets=1, annotation_sets=1)"
    assert str(resolved_dataset) == "ResolvedDatasetVersion(dataset=demo, version=0.1.0, datums=1)"


def test_annotation_schema_and_label_definition_defaults():
    label = AnnotationLabelDefinition(name="cat", id=1, color="#ffffff")
    schema = AnnotationSchema(
        name="demo-schema",
        version="1.0.0",
        task_type="classification",
        allowed_annotation_kinds=["classification"],
        labels=[label],
    )
    annotation_set = AnnotationSet(
        name="gt",
        purpose="ground_truth",
        source_type="human",
        annotation_schema_id=schema.annotation_schema_id,
    )

    assert label.metadata == {}
    assert str(label) == "AnnotationLabelDefinition(name=cat, id=1)"
    assert schema.allow_scores is False
    assert schema.required_attributes == []
    assert schema.optional_attributes == []
    assert schema.allow_additional_attributes is False
    assert "AnnotationSchema(annotation_schema_id=" in str(schema)
    assert annotation_set.annotation_schema_id == schema.annotation_schema_id

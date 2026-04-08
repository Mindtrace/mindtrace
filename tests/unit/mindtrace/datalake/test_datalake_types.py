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
    record = AnnotationRecord(kind="bbox", label="dent", source={"type": "human", "name": "review-ui"}, geometry={})
    annotation_set = AnnotationSet(name="gt", purpose="ground_truth", source_type="human")
    datum = Datum(asset_refs={"image": asset.asset_id}, split="train")
    dataset_version = DatasetVersion(dataset_name="demo", version="0.1.0", manifest=[datum.datum_id])
    resolved_datum = ResolvedDatum(datum=datum, assets={"image": asset}, annotation_sets=[annotation_set])
    resolved_dataset = ResolvedDatasetVersion(dataset_version=dataset_version, datums=[resolved_datum])

    assert "Asset(asset_id=" in str(asset)
    assert "AnnotationRecord(annotation_id=" in str(record)
    assert "AnnotationSet(annotation_set_id=" in str(annotation_set)
    assert "Datum(datum_id=" in str(datum)
    assert str(dataset_version) == "DatasetVersion(dataset=demo, version=0.1.0, datums=1)"
    assert str(resolved_datum) == f"ResolvedDatum(datum_id={datum.datum_id}, assets=1, annotation_sets=1)"
    assert str(resolved_dataset) == "ResolvedDatasetVersion(dataset=demo, version=0.1.0, datums=1)"

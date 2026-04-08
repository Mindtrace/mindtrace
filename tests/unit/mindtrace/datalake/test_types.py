from mindtrace.datalake.types import AnnotationSource, StorageRef, SubjectRef


def test_storage_ref_builds_qualified_key():
    ref = StorageRef(mount="nas", name="images/cat.jpg", version="v1")

    assert ref.qualified_key == "nas/images/cat.jpg@v1"


def test_subject_ref_accepts_asset_and_annotation_kinds():
    asset_subject = SubjectRef(kind="asset", id="asset_123")
    annotation_subject = SubjectRef(kind="annotation", id="annotation_123")

    assert asset_subject.kind == "asset"
    assert annotation_subject.kind == "annotation"


def test_annotation_source_defaults_metadata():
    source = AnnotationSource(type="machine", name="detector", version="1.0.0")

    assert source.metadata == {}

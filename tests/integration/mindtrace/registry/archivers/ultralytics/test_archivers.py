import os
import tempfile

from ultralytics import SAM, YOLO, YOLOE

from mindtrace.registry.archivers.ultralytics.sam_archiver import SamArchiver
from mindtrace.registry.archivers.ultralytics.yolo_archiver import YoloArchiver
from mindtrace.registry.archivers.ultralytics.yoloe_archiver import YoloEArchiver

MINIO_BUCKET = os.environ.get("MINIO_BUCKET", "minio-registry")


def minio_uri(prefix):
    # Minio URI format: s3://bucket/prefix
    return f"s3://{MINIO_BUCKET}/{prefix}"


def test_yolo_archiver_minio(minio_registry, mock_assets):
    # Download smallest YOLO model
    with tempfile.TemporaryDirectory() as tmpdir:
        # Download the smallest YOLO model
        model = YOLO(os.path.join(tmpdir, "yolov8n.pt"))

        # Set the registry to use the YoloArchiver
        minio_registry.register_materializer(YOLO, YoloArchiver)

        # Save to Minio using YoloArchiver
        prefix = "tests:integration:yolo-archiver"
        minio_registry.save(name=prefix, obj=model)

        # Check model is in registry
        assert prefix in minio_registry

        # Load back
        loaded = minio_registry.load(prefix)
        assert isinstance(loaded, YOLO)

        # Run inference on a test image
        PERSON_CLASS_ID = 0
        results = loaded.predict(mock_assets.image)
        assert results[0].names[PERSON_CLASS_ID] == "person", "The test does not have the right person class ID"
        assert PERSON_CLASS_ID in results[0].boxes.cls, "Model did not find a person in the image"


def test_yoloe_archiver_minio(minio_registry, mock_assets):
    # Download smallest YOLOE model
    with tempfile.TemporaryDirectory() as tmpdir:
        model = YOLOE(os.path.join(tmpdir, "yoloe-v8s-seg-pf.pt"))

        # Set the registry to use the YoloEArchiver
        minio_registry.register_materializer(YOLOE, YoloEArchiver)

        # Save to Minio using YoloEArchiver
        prefix = "tests:integration:yoloe-archiver"
        minio_registry.save(name=prefix, obj=model)

        # Check model is in registry
        assert prefix in minio_registry

        # Load back
        loaded = minio_registry.load(prefix)
        assert isinstance(loaded, YOLOE)

        # Run inference on a test image (segmentation)
        PERSON_CLASS_ID = 2163
        results = loaded.predict(mock_assets.image)
        assert results[0].names[PERSON_CLASS_ID] == "person", "The test does not have the right person class ID"
        assert PERSON_CLASS_ID in results[0].boxes.cls, "Model did not find a person in the image"


def test_sam_archiver_minio(minio_registry, mock_assets):
    # Download smallest SAM model
    with tempfile.TemporaryDirectory() as tmpdir:
        model = SAM(os.path.join(tmpdir, "sam2.1_t.pt"))

        # Set the registry to use the SamArchiver
        minio_registry.register_materializer(SAM, SamArchiver)

        # Save to Minio using SamArchiver
        prefix = "tests:integration:sam-archiver"
        minio_registry.save(name=prefix, obj=model)

        # Check model is in registry
        assert prefix in minio_registry

        # Load back
        loaded = minio_registry.load(prefix)
        assert isinstance(loaded, SAM)

        # Run inference on a test image (segmentation)
        results = loaded.predict(mock_assets.image)
        assert len(results[0].boxes) > 0, "Model did not find any objects in the image"

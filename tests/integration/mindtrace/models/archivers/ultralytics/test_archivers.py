import os
import socket
import tempfile
import urllib.request

import pytest
from ultralytics import SAM, YOLO, YOLOE

from mindtrace.models.archivers.ultralytics.sam_archiver import SamArchiver
from mindtrace.models.archivers.ultralytics.yolo_archiver import YoloArchiver
from mindtrace.models.archivers.ultralytics.yoloe_archiver import YoloEArchiver


def check_ultralytics_connectivity(timeout=10):
    """Check if ultralytics model download servers are reachable.

    Args:
        timeout: Connection timeout in seconds

    Returns:
        bool: True if servers are reachable, False otherwise
    """
    # Primary servers that ultralytics uses for model downloads
    servers_to_check = [
        ("github.com", 443),  # GitHub releases (primary model host)
        ("api.github.com", 443),  # GitHub API
        ("objects.githubusercontent.com", 443),  # GitHub raw content
    ]

    for host, port in servers_to_check:
        try:
            # Test TCP connection
            with socket.create_connection((host, port), timeout=timeout):
                pass

            # Test HTTP(S) connectivity for at least one server
            if host == "github.com":
                try:
                    with urllib.request.urlopen(f"https://{host}", timeout=timeout) as response:
                        if response.getcode() == 200:
                            return True
                except Exception:
                    continue
            else:
                return True  # TCP connection succeeded

        except (socket.timeout, socket.error, OSError):
            continue

    return False


# Skip all tests in this module if ultralytics servers are unreachable
pytestmark = pytest.mark.skipif(
    not check_ultralytics_connectivity(),
    reason="Ultralytics model download servers are not reachable (requires internet connection)",
)


def test_yolo_archiver_s3(s3_registry, mock_assets):
    # Download smallest YOLO model
    with tempfile.TemporaryDirectory() as tmpdir:
        # Download the smallest YOLO model
        model = YOLO(os.path.join(tmpdir, "yolov8n.pt"))

        # Set the registry to use the YoloArchiver
        s3_registry.register_materializer(YOLO, YoloArchiver)

        # Save to S3 using YoloArchiver
        prefix = "tests:integration:yolo-archiver"
        s3_registry.save(name=prefix, obj=model)

        # Check model is in registry
        assert prefix in s3_registry

        # Load back
        loaded = s3_registry.load(prefix)
        assert isinstance(loaded, YOLO)

        # Run inference on a test image
        PERSON_CLASS_ID = 0
        results = loaded.predict(mock_assets.image)
        assert results[0].names[PERSON_CLASS_ID] == "person", "The test does not have the right person class ID"
        assert PERSON_CLASS_ID in results[0].boxes.cls, "Model did not find a person in the image"


def test_yoloe_archiver_s3(s3_registry, mock_assets):
    # Download smallest YOLOE model
    with tempfile.TemporaryDirectory() as tmpdir:
        model = YOLOE(os.path.join(tmpdir, "yoloe-v8s-seg-pf.pt"))

        # Set the registry to use the YoloEArchiver
        s3_registry.register_materializer(YOLOE, YoloEArchiver)

        # Save to S3 using YoloEArchiver
        prefix = "tests:integration:yoloe-archiver"
        s3_registry.save(name=prefix, obj=model)

        # Check model is in registry
        assert prefix in s3_registry

        # Load back
        loaded = s3_registry.load(prefix)
        assert isinstance(loaded, YOLOE)

        # Run inference on a test image (segmentation)
        PERSON_CLASS_ID = 2163
        results = loaded.predict(mock_assets.image)
        assert results[0].names[PERSON_CLASS_ID] == "person", "The test does not have the right person class ID"
        assert PERSON_CLASS_ID in results[0].boxes.cls, "Model did not find a person in the image"


def test_sam_archiver_s3(s3_registry, mock_assets):
    # Download smallest SAM model
    with tempfile.TemporaryDirectory() as tmpdir:
        model = SAM(os.path.join(tmpdir, "sam2.1_t.pt"))

        # Set the registry to use the SamArchiver
        s3_registry.register_materializer(SAM, SamArchiver)

        # Save to S3 using SamArchiver
        prefix = "tests:integration:sam-archiver"
        s3_registry.save(name=prefix, obj=model)

        # Check model is in registry
        assert prefix in s3_registry

        # Load back
        loaded = s3_registry.load(prefix)
        assert isinstance(loaded, SAM)

        # Run inference on a test image (segmentation)
        results = loaded.predict(mock_assets.image)
        assert len(results[0].boxes) > 0, "Model did not find any objects in the image"

import argparse
import os
from PIL import Image
import tempfile

from mindtrace.registry import Registry, MinioRegistryBackend

# Model variants and their associated tasks
YOLO_VARIANTS = [
    ("", "Detection"),
    ("-seg", "Segmentation"),
    ("-cls", "Classification"),
    ("-pose", "Pose"),
    ("-obb", "Oriented Detection"),
]

# Model sizes
YOLO_SIZES = ["n", "s", "m", "l", "x"]

# Model versions and which variants they support
YOLO_MODELS = {
    "yolov8": YOLO_VARIANTS,  # all variants
    "yolov10": [("", "Detection")],  # detection only
    "yolo11": YOLO_VARIANTS,  # all variants
    "yolo12": [("", "Detection")],  # detection only
}


def main():
    parser = argparse.ArgumentParser(description="Populate the model registry with Ultralytics YOLO models.")
    parser.add_argument(
        "--backend",
        choices=["local", "minio"],
        default="local",
        help="Registry backend type.",
    )
    parser.add_argument(
        "--registry-path",
        type=str,
        help="Path to the model registry directory (for local backend).",
    )
    parser.add_argument(
        "--minio-endpoint",
        type=str,
        help="MinIO endpoint (for minio backend).",
    )
    parser.add_argument(
        "--minio-access-key",
        type=str,
        help="MinIO access key (for minio backend).",
    )
    parser.add_argument(
        "--minio-secret-key",
        type=str,
        help="MinIO secret key (for minio backend).",
    )
    parser.add_argument(
        "--minio-bucket",
        type=str,
        help="MinIO bucket (for minio backend).",
    )
    parser.add_argument(
        "--minio-uri",
        type=str,
        help="MinIO URI (for minio backend).",
    )
    parser.add_argument(
        "--minio-secure",
        action="store_true",
        help="Use secure connection for MinIO (for minio backend).",
    )
    args = parser.parse_args()

    if args.backend == "local":
        if not args.registry_path:
            parser.error("--registry-path is required for local backend")
        registry = Registry(registry_dir=args.registry_path)
    elif args.backend == "minio":
        required = [
            "minio_endpoint",
            "minio_access_key",
            "minio_secret_key",
            "minio_bucket",
            "minio_uri",
        ]
        for r in required:
            if getattr(args, r) is None:
                parser.error(f"--{r.replace('_', '-')} is required for minio backend")
        minio_backend = MinioRegistryBackend(
            uri=args.minio_uri,
            endpoint=args.minio_endpoint,
            access_key=args.minio_access_key,
            secret_key=args.minio_secret_key,
            bucket=args.minio_bucket,
            secure=args.minio_secure,
        )
        registry = Registry(backend=minio_backend)
    else:
        parser.error("Unknown backend type")

    with tempfile.TemporaryDirectory() as temp_dir:
        # Set the weights directory to the temporary directory before importing ultralytics
        os.environ["ULTRALYTICS_WEIGHTS_DIR"] = temp_dir
        from ultralytics import YOLO

        for version, variants in YOLO_MODELS.items():
            for size in YOLO_SIZES:
                for suffix, task in variants:
                    model_filename = f"{version}{size}{suffix}.pt"
                    key = f"models:ultralytics:{version}:{size}{suffix}"
                    print(f"Registering {model_filename} as {key} (Task: {task})")
                    try:
                        model = YOLO(model_filename, task=None)
                        if "v" in version:
                            key = key.replace("v", "")  # remove the v from the version name, if present
                        registry.save(key, model, metadata={"Task": task})
                        print(f"Registered: {key}")
                    except Exception as e:
                        print(f"Failed to register {key}: {e}")

    # Register a test image
    print(f"Registering Hopper image as images:hopper")
    try:
        image = Image.open("tests/resources/hopper.png")
        registry.save(
            "images:hopper",
            image,
            metadata={
                "Description": "Self-portrait of Edward Hopper in a suit and tie. Useful for testing YOLO models.",
                "Source": "tests/resources/hopper.png"
            },
        )
        print("Registered: images:hopper")
    except Exception as e:
        print(f"Failed to register images:hopper: {e}")

if __name__ == "__main__":
    main()

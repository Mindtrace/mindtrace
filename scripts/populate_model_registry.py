"""Populate the model registry with Ultralytics YOLO, YOLOE, and SAM models.
"""
import argparse
import os
from PIL import Image
import tempfile

import ultralytics

from mindtrace.registry import Registry, MinioRegistryBackend

EXAMPLES = """
Examples:

  # Show help and all options
  uv run python scripts/populate_model_registry.py --help

  # Populate a local registry
  uv run python scripts/populate_model_registry.py \\
      --backend local \\
      --registry-path ~/.cache/mindtrace/model-registry

  # Populate a MinIO registry and cache models
  uv run python scripts/populate_model_registry.py \\
      --backend minio \\
      --minio-endpoint localhost:9000 \\
      --minio-access-key minioadmin \\
      --minio-secret-key minioadmin \\
      --minio-bucket model-registry \\
      --minio-uri ~/.cache/mindtrace/model-registry \\
      --cache-models
"""

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

YOLO_WORLD_MODELS = [
    "yolov8s-world",
    "yolov8s-worldv2",
    "yolov8m-world",
    "yolov8m-worldv2",
    "yolov8l-world",
    "yolov8l-worldv2",
    "yolov8x-world",
    "yolov8x-worldv2",
]

YOLOE_SIZES = ["s", "m", "l"]

YOLOE_VARIANTS = [
    ("-seg", "Segmentation"),
    ("-seg-pf", "Segmentation"),
]

YOLOE_MODELS = [
    "yoloe-v8",
    "yoloe-11",
]

SAM_MODELS = [
    "sam_b", 
    "sam_l", 
    "sam2_t", 
    "sam2_s", 
    "sam2_b", 
    "sam2_l", 
    "sam2.1_t", 
    "sam2.1_s", 
    "sam2.1_b", 
    "sam2.1_l"
]


def main():
    parser = argparse.ArgumentParser(
        description="Populate the model registry with Ultralytics YOLO, YOLOE, and SAM models.\n\n" + EXAMPLES,
        formatter_class=argparse.RawTextHelpFormatter,
    )
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
    parser.add_argument(
        "--cache-models",
        action="store_true",
        help="Downloaded models will not be discarded after the script is run, but kept in the "
            "'~/.cache/mindtrace/models' cache directory.",
    )
    args = parser.parse_args()

    registry = init_registry(args, parser)

    with tempfile.TemporaryDirectory() as temp_dir:
        if args.cache_models:
            temp_dir = os.path.expanduser("~/.cache/mindtrace/models")
        register_test_image(registry)
        register_yolo_models(registry, temp_dir)
        register_yolo_world_models(registry, temp_dir)
        register_yolo_e_models(registry, temp_dir)
        register_sam_models(registry, temp_dir)


def init_registry(args: argparse.Namespace, parser: argparse.ArgumentParser) -> Registry:
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

    return registry


def register_test_image(registry: Registry):
    print(f"\nRegistering Hopper image as images:hopper")
    try:
        image = Image.open("tests/resources/hopper.png")
        registry.save(
            "data:images:hopper",
            image,
            metadata={
                "Description": "Self-portrait of Edward Hopper in a suit and tie.",
                "Source": "tests/resources/hopper.png"
            },
        )
        print("Registered: data:images:hopper")
    except Exception as e:
        print(f"Failed to register data:images:hopper: {e}")


def register_yolo_models(registry: Registry, dir_path: str):
    from ultralytics import YOLO
    print("\nRegistering YOLO models...")
    for version, variants in YOLO_MODELS.items():
        for size in YOLO_SIZES:
            for suffix, task in variants:
                model_filename = f"{version}{size}{suffix}.pt"
                key = f"models:ultralytics:{version}:{size}{suffix}"
                print(f"Registering {model_filename} as {key} (Task: {task})")
                try:
                    reg_key = key.replace("v", "")  # remove the v from the version name, if present
                    if key not in registry:
                        yolo = YOLO(os.path.join(dir_path, model_filename), task=None)
                        registry.save(key, yolo, metadata={"Task": task})
                    print(f"Registered: {key}")
                except Exception as e:
                    print(f"Failed to register {key}: {e}")


def register_yolo_world_models(registry: Registry, dir_path: str):
    from ultralytics import YOLO
    print("\nRegistering YOLO-World models...")
    for model in YOLO_WORLD_MODELS:
        model_filename = f"{model}.pt"
        key = f"models:ultralytics:{model.replace('_', ':').replace('v', '')}"
        size = key[24]
        key = key[:24] + key[25:] + ":" + size
        print(f"Registering {model_filename} as {key} (Task: Detection)")
        try:
            if key not in registry:
                yolo = YOLO(os.path.join(dir_path, model_filename), task=None)
                registry.save(key, yolo, metadata={"Task": "Detection"})
            print(f"Registered: {key}")
        except Exception as e:
            print(f"Failed to register {key}: {e}")


def register_yolo_e_models(registry: Registry, dir_path: str):
    from ultralytics import YOLOE
    print("\nRegistering YOLO-E models...")
    for model in YOLOE_MODELS:
        for size in YOLOE_SIZES:
            for suffix, task in YOLOE_VARIANTS:
                model_filename = f"{model}{size}{suffix}.pt"
                key = f"models:ultralytics:{model}{suffix}:{size}"
                print(f"Registering {model_filename} as {key} (Task: {task})")
                try:
                    if key not in registry:
                        yolo = YOLOE(os.path.join(dir_path, model_filename), task=None)
                        registry.save(key, yolo, metadata={"Task": task})
                    print(f"Registered: {key}")
                except Exception as e:
                    print(f"Failed to register {key}: {e}")


def register_sam_models(registry: Registry, dir_path: str):
    from ultralytics import SAM
    print("\nRegistering SAM models...")
    for model in SAM_MODELS:
        model_filename = f"{model}.pt"
        key = f"models:ultralytics:{model.replace("_", ":")}"
        print(f"Registering {model_filename} as {key} (Task: Segmentation)")
        try:
            if key not in registry:
                sam = SAM(os.path.join(dir_path, model_filename))
                registry.save(key, sam, metadata={"Task": "Segmentation"})
            print(f"Registered: {key}")
        except Exception as e:
            print(f"Failed to register {key}: {e}")

 
if __name__ == "__main__":
    main()

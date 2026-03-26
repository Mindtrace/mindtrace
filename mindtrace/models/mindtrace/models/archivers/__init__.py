"""ML model archivers.

Serialization/deserialization of ML model formats (HuggingFace, timm,
Ultralytics, ONNX). Each archiver self-registers with the
Registry at import time via Registry.register_default_materializer().
"""


def register_ml_archivers() -> None:
    """Import all ML archiver modules to trigger their self-registration."""
    # HuggingFace (guards internally via try/except)
    try:
        import mindtrace.models.archivers.huggingface.hf_model_archiver  # noqa: F401
        import mindtrace.models.archivers.huggingface.hf_processor_archiver  # noqa: F401
    except ImportError:
        pass

    # ONNX (guards internally via try/except)
    try:
        import mindtrace.models.archivers.onnx.onnx_model_archiver  # noqa: F401
    except ImportError:
        pass

    # timm
    try:
        import mindtrace.models.archivers.timm.timm_model_archiver  # noqa: F401
    except ImportError:
        pass

    # Ultralytics
    try:
        import mindtrace.models.archivers.ultralytics.sam_archiver  # noqa: F401
        import mindtrace.models.archivers.ultralytics.yolo_archiver  # noqa: F401
        import mindtrace.models.archivers.ultralytics.yoloe_archiver  # noqa: F401
    except ImportError:
        pass


register_ml_archivers()

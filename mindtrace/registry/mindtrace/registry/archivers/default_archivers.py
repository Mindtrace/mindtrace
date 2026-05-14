from pathlib import Path, PosixPath, WindowsPath

from mindtrace.registry.archivers.path_archiver import PathArchiver
from mindtrace.registry.core.registry import Registry

_BUILTIN = "mindtrace.registry.archivers.builtin_materializers"
_INTEGRATION = "mindtrace.registry.archivers.integration_materializers"


def register_default_materializers():
    # Core built-in materializers.
    Registry.register_default_materializer("builtins.str", f"{_BUILTIN}.BuiltInMaterializer")
    Registry.register_default_materializer("builtins.int", f"{_BUILTIN}.BuiltInMaterializer")
    Registry.register_default_materializer("builtins.float", f"{_BUILTIN}.BuiltInMaterializer")
    Registry.register_default_materializer("builtins.bool", f"{_BUILTIN}.BuiltInMaterializer")
    Registry.register_default_materializer("builtins.list", f"{_BUILTIN}.BuiltInContainerMaterializer")
    Registry.register_default_materializer("builtins.dict", f"{_BUILTIN}.BuiltInContainerMaterializer")
    Registry.register_default_materializer("builtins.tuple", f"{_BUILTIN}.BuiltInContainerMaterializer")
    Registry.register_default_materializer("builtins.set", f"{_BUILTIN}.BuiltInContainerMaterializer")
    Registry.register_default_materializer("builtins.bytes", f"{_BUILTIN}.BytesMaterializer")
    # Pydantic re-exports ``BaseModel`` from the package root, but the class's real
    # ``__module__`` is ``pydantic.main`` — register both so MRO-based dispatch hits.
    Registry.register_default_materializer("pydantic.BaseModel", f"{_BUILTIN}.PydanticMaterializer")
    Registry.register_default_materializer("pydantic.main.BaseModel", f"{_BUILTIN}.PydanticMaterializer")

    # Path types - use PathArchiver to preserve original filenames
    Registry.register_default_materializer(Path, PathArchiver)
    Registry.register_default_materializer(PosixPath, PathArchiver)
    Registry.register_default_materializer(WindowsPath, PathArchiver)

    # Core mindtrace materializers
    Registry.register_default_materializer(
        "mindtrace.core.config.config.Config", "mindtrace.registry.archivers.config_archiver.ConfigArchiver"
    )

    # (Optional) HuggingFace datasets — register both the public import path and
    # the real ``__module__`` path so MRO-based dispatch hits.
    Registry.register_default_materializer("datasets.Dataset", f"{_INTEGRATION}.HFDatasetMaterializer")
    Registry.register_default_materializer("datasets.arrow_dataset.Dataset", f"{_INTEGRATION}.HFDatasetMaterializer")
    Registry.register_default_materializer("datasets.DatasetDict", f"{_INTEGRATION}.HFDatasetMaterializer")
    Registry.register_default_materializer("datasets.dataset_dict.DatasetDict", f"{_INTEGRATION}.HFDatasetMaterializer")
    Registry.register_default_materializer("datasets.IterableDataset", f"{_INTEGRATION}.HFDatasetMaterializer")
    Registry.register_default_materializer(
        "datasets.iterable_dataset.IterableDataset", f"{_INTEGRATION}.HFDatasetMaterializer"
    )

    # (Optional) NumPy
    Registry.register_default_materializer("numpy.ndarray", f"{_INTEGRATION}.NumpyMaterializer")

    # (Optional) Pillow
    Registry.register_default_materializer("PIL.Image.Image", f"{_INTEGRATION}.PillowImageMaterializer")

    # (Optional) PyTorch
    Registry.register_default_materializer(
        "torch.utils.data.DataLoader", f"{_INTEGRATION}.PyTorchDataLoaderMaterializer"
    )
    Registry.register_default_materializer("torch.utils.data.Dataset", f"{_INTEGRATION}.PyTorchDataLoaderMaterializer")
    Registry.register_default_materializer(
        "torch.utils.data.IterableDataset", f"{_INTEGRATION}.PyTorchDataLoaderMaterializer"
    )
    Registry.register_default_materializer(
        "torch.nn.modules.module.Module", f"{_INTEGRATION}.PyTorchModuleMaterializer"
    )
    Registry.register_default_materializer(
        "torch.jit._script.ScriptModule", f"{_INTEGRATION}.PyTorchModuleMaterializer"
    )

    # ── ML framework archivers (string-based for lazy loading) ──────────
    # The archiver classes live in mindtrace.models.archivers and are only
    # imported when instantiate_target() resolves them during save/load.

    # Ultralytics
    Registry.register_default_materializer(
        "ultralytics.models.sam.model.SAM",
        "mindtrace.models.archivers.ultralytics.sam_archiver.SamArchiver",
    )
    Registry.register_default_materializer(
        "ultralytics.models.yolo.model.YOLO",
        "mindtrace.models.archivers.ultralytics.yolo_archiver.YoloArchiver",
    )
    Registry.register_default_materializer(
        "ultralytics.models.yolo.model.YOLOWorld",
        "mindtrace.models.archivers.ultralytics.yolo_archiver.YoloArchiver",
    )
    Registry.register_default_materializer(
        "ultralytics.models.yolo.model.YOLOE",
        "mindtrace.models.archivers.ultralytics.yoloe_archiver.YoloEArchiver",
    )

    # HuggingFace models
    Registry.register_default_materializer(
        "transformers.modeling_utils.PreTrainedModel",
        "mindtrace.models.archivers.huggingface.hf_model_archiver.HuggingFaceModelArchiver",
    )
    Registry.register_default_materializer(
        "peft.peft_model.PeftModel",
        "mindtrace.models.archivers.huggingface.hf_model_archiver.HuggingFaceModelArchiver",
    )

    # HuggingFace processors
    Registry.register_default_materializer(
        "transformers.tokenization_utils_base.PreTrainedTokenizerBase",
        "mindtrace.models.archivers.huggingface.hf_processor_archiver.HuggingFaceProcessorArchiver",
    )
    Registry.register_default_materializer(
        "transformers.processing_utils.ProcessorMixin",
        "mindtrace.models.archivers.huggingface.hf_processor_archiver.HuggingFaceProcessorArchiver",
    )
    Registry.register_default_materializer(
        "transformers.image_processing_base.ImageProcessingMixin",
        "mindtrace.models.archivers.huggingface.hf_processor_archiver.HuggingFaceProcessorArchiver",
    )
    Registry.register_default_materializer(
        "transformers.feature_extraction_utils.FeatureExtractionMixin",
        "mindtrace.models.archivers.huggingface.hf_processor_archiver.HuggingFaceProcessorArchiver",
    )

    # ONNX
    Registry.register_default_materializer(
        "onnx.onnx_ml_pb2.ModelProto",
        "mindtrace.models.archivers.onnx.onnx_model_archiver.OnnxModelArchiver",
    )

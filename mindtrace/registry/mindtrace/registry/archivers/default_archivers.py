from pathlib import Path, PosixPath, WindowsPath

from mindtrace.registry.archivers.path_archiver import PathArchiver
from mindtrace.registry.core.registry import Registry


def register_default_materializers():
    # Built-in types
    Registry.register_default_materializer(
        "builtins.str", "mindtrace.registry.archivers.builtin_materializers.BuiltInMaterializer"
    )
    Registry.register_default_materializer(
        "builtins.int", "mindtrace.registry.archivers.builtin_materializers.BuiltInMaterializer"
    )
    Registry.register_default_materializer(
        "builtins.float", "mindtrace.registry.archivers.builtin_materializers.BuiltInMaterializer"
    )
    Registry.register_default_materializer(
        "builtins.bool", "mindtrace.registry.archivers.builtin_materializers.BuiltInMaterializer"
    )
    Registry.register_default_materializer(
        "builtins.list", "mindtrace.registry.archivers.builtin_materializers.BuiltInContainerMaterializer"
    )
    Registry.register_default_materializer(
        "builtins.dict", "mindtrace.registry.archivers.builtin_materializers.BuiltInContainerMaterializer"
    )
    Registry.register_default_materializer(
        "builtins.tuple", "mindtrace.registry.archivers.builtin_materializers.BuiltInContainerMaterializer"
    )
    Registry.register_default_materializer(
        "builtins.set", "mindtrace.registry.archivers.builtin_materializers.BuiltInContainerMaterializer"
    )
    Registry.register_default_materializer(
        "builtins.bytes", "mindtrace.registry.archivers.builtin_materializers.BytesMaterializer"
    )
    Registry.register_default_materializer(
        "pydantic.main.BaseModel", "mindtrace.registry.archivers.builtin_materializers.PydanticMaterializer"
    )
    # Path types - use PathArchiver to preserve original filenames
    Registry.register_default_materializer(Path, PathArchiver)
    Registry.register_default_materializer(PosixPath, PathArchiver)
    Registry.register_default_materializer(WindowsPath, PathArchiver)

    # Core mindtrace materializers
    Registry.register_default_materializer(
        "mindtrace.core.config.config.Config", "mindtrace.registry.archivers.config_archiver.ConfigArchiver"
    )
    Registry.register_default_materializer(
        "mindtrace.jobs.local.fifo_queue.LocalQueue",
        "mindtrace.jobs.archivers.LocalQueueArchiver",
    )
    Registry.register_default_materializer(
        "mindtrace.jobs.local.priority_queue.LocalPriorityQueue",
        "mindtrace.jobs.archivers.PriorityQueueArchiver",
    )
    Registry.register_default_materializer(
        "mindtrace.jobs.local.stack.LocalStack",
        "mindtrace.jobs.archivers.StackArchiver",
    )

    # (Optional) HuggingFace datasets
    Registry.register_default_materializer(
        "datasets.Dataset",
        "mindtrace.registry.archivers.integration_materializers.HFDatasetMaterializer",
    )
    Registry.register_default_materializer(
        "datasets.DatasetDict",
        "mindtrace.registry.archivers.integration_materializers.HFDatasetMaterializer",
    )
    Registry.register_default_materializer(
        "datasets.IterableDataset",
        "mindtrace.registry.archivers.integration_materializers.HFDatasetMaterializer",
    )

    # (Optional) NumPy
    Registry.register_default_materializer(
        "numpy.ndarray", "mindtrace.registry.archivers.integration_materializers.NumpyMaterializer"
    )

    # (Optional) Pillow
    Registry.register_default_materializer(
        "PIL.Image.Image",
        "mindtrace.registry.archivers.integration_materializers.PillowImageMaterializer",
    )

    # (Optional) PyTorch
    Registry.register_default_materializer(
        "torch.utils.data.DataLoader",
        "mindtrace.registry.archivers.integration_materializers.PyTorchDataLoaderMaterializer",
    )
    Registry.register_default_materializer(
        "torch.utils.data.Dataset",
        "mindtrace.registry.archivers.integration_materializers.PyTorchDataLoaderMaterializer",
    )
    Registry.register_default_materializer(
        "torch.utils.data.IterableDataset",
        "mindtrace.registry.archivers.integration_materializers.PyTorchDataLoaderMaterializer",
    )
    Registry.register_default_materializer(
        "torch.nn.modules.module.Module",
        "mindtrace.registry.archivers.integration_materializers.PyTorchModuleMaterializer",
    )
    Registry.register_default_materializer(
        "torch.jit._script.ScriptModule",
        "mindtrace.registry.archivers.integration_materializers.PyTorchModuleMaterializer",
    )

    # ── ML framework archivers (string-based for lazy loading) ──────────

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
        "transformers.PreTrainedModel",
        "mindtrace.models.archivers.huggingface.hf_model_archiver.HuggingFaceModelArchiver",
    )
    Registry.register_default_materializer(
        "transformers.TFPreTrainedModel",
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

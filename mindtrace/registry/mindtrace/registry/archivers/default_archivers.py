from pathlib import Path, PosixPath, WindowsPath

from mindtrace.registry.archivers.path_archiver import PathArchiver
from mindtrace.registry.core.registry import Registry


def register_default_materializers():
    # Core zenml materializers
    Registry.register_default_materializer(
        "builtins.str", "zenml.materializers.built_in_materializer.BuiltInMaterializer"
    )
    Registry.register_default_materializer(
        "builtins.int", "zenml.materializers.built_in_materializer.BuiltInMaterializer"
    )
    Registry.register_default_materializer(
        "builtins.float", "zenml.materializers.built_in_materializer.BuiltInMaterializer"
    )
    Registry.register_default_materializer(
        "builtins.bool", "zenml.materializers.built_in_materializer.BuiltInMaterializer"
    )
    Registry.register_default_materializer("builtins.list", "zenml.materializers.BuiltInContainerMaterializer")
    Registry.register_default_materializer("builtins.dict", "zenml.materializers.BuiltInContainerMaterializer")
    Registry.register_default_materializer("builtins.tuple", "zenml.materializers.BuiltInContainerMaterializer")
    Registry.register_default_materializer("builtins.set", "zenml.materializers.BuiltInContainerMaterializer")
    Registry.register_default_materializer("builtins.bytes", "zenml.materializers.BytesMaterializer")
    Registry.register_default_materializer("pydantic.BaseModel", "zenml.materializers.PydanticMaterializer")
    # Path types - use PathArchiver to preserve original filenames
    Registry.register_default_materializer(Path, PathArchiver)
    Registry.register_default_materializer(PosixPath, PathArchiver)
    Registry.register_default_materializer(WindowsPath, PathArchiver)

    # Core mindtrace materializers
    Registry.register_default_materializer(
        "mindtrace.core.config.config.Config", "mindtrace.registry.archivers.config_archiver.ConfigArchiver"
    )

    # (Optional) Huggingface materializers
    Registry.register_default_materializer(
        "datasets.Dataset",
        "zenml.integrations.huggingface.materializers.huggingface_datasets_materializer.HFDatasetMaterializer",
    )
    Registry.register_default_materializer(
        "datasets.DatasetDict",
        "zenml.integrations.huggingface.materializers.huggingface_datasets_materializer.HFDatasetMaterializer",
    )
    Registry.register_default_materializer(
        "datasets.IterableDataset",
        "zenml.integrations.huggingface.materializers.huggingface_datasets_materializer.HFDatasetMaterializer",
    )
    Registry.register_default_materializer(
        "transformers.PreTrainedModel",
        "zenml.integrations.huggingface.materializers.huggingface_pt_model_materializer.HFPTModelMaterializer",
    )
    Registry.register_default_materializer(
        "transformers.TFPreTrainedModel",
        "zenml.integrations.huggingface.materializers.huggingface_pt_model_materializer.HFPTModelMaterializer",
    )

    # (Optional) NumPy materializers
    Registry.register_default_materializer(
        "numpy.ndarray", "zenml.integrations.numpy.materializers.numpy_materializer.NumpyMaterializer"
    )

    # (Optional) Pillow materializers
    Registry.register_default_materializer(
        "PIL.Image.Image",
        "zenml.integrations.pillow.materializers.pillow_image_materializer.PillowImageMaterializer",
    )

    # (Optional) PyTorch materializers
    Registry.register_default_materializer(
        "torch.utils.data.DataLoader",
        "zenml.integrations.pytorch.materializers.pytorch_dataloader_materializer.PyTorchDataLoaderMaterializer",
    )
    Registry.register_default_materializer(
        "torch.utils.data.Dataset",
        "zenml.integrations.pytorch.materializers.pytorch_dataloader_materializer.PyTorchDataLoaderMaterializer",
    )
    Registry.register_default_materializer(
        "torch.utils.data.IterableDataset",
        "zenml.integrations.pytorch.materializers.pytorch_dataloader_materializer.PyTorchDataLoaderMaterializer",
    )
    Registry.register_default_materializer(
        "torch.nn.Module",
        "zenml.integrations.pytorch.materializers.pytorch_module_materializer.PyTorchModuleMaterializer",
    )
    Registry.register_default_materializer(
        "torch.jit.ScriptModule",
        "zenml.integrations.pytorch.materializers.pytorch_module_materializer.PyTorchModuleMaterializer",
    )

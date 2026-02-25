"""HuggingFace model archivers for mindtrace Registry."""

from mindtrace.registry.archivers.huggingface.hf_model_archiver import (
    HuggingFaceModelArchiver,
)
from mindtrace.registry.archivers.huggingface.hf_processor_archiver import (
    HuggingFaceProcessorArchiver,
)

__all__ = ["HuggingFaceModelArchiver", "HuggingFaceProcessorArchiver"]

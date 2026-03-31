"""HuggingFace model archivers for mindtrace Registry."""

from mindtrace.models.archivers.huggingface.hf_model_archiver import (
    HuggingFaceModelArchiver,
)
from mindtrace.models.archivers.huggingface.hf_processor_archiver import (
    HuggingFaceProcessorArchiver,
)

__all__ = ["HuggingFaceModelArchiver", "HuggingFaceProcessorArchiver"]

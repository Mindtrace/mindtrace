"""Archiver for HuggingFace Processors and Tokenizers.

Handles saving and loading of:
- AutoProcessor
- AutoTokenizer
- AutoImageProcessor
- AutoFeatureExtractor
"""

import os
from typing import Any, ClassVar, Tuple, Type

from zenml.enums import ArtifactType

from mindtrace.registry import Archiver, Registry

# Check if transformers is available
try:
    from transformers import (
        PreTrainedTokenizerBase,
        ProcessorMixin,
        ImageProcessingMixin,
        FeatureExtractionMixin,
    )
    _HF_AVAILABLE = True
    _HF_PROCESSOR_TYPES: Tuple[Type[Any], ...] = (
        PreTrainedTokenizerBase,
        ProcessorMixin,
        ImageProcessingMixin,
        FeatureExtractionMixin,
    )
except ImportError:
    _HF_AVAILABLE = False
    _HF_PROCESSOR_TYPES = (object,)  # Fallback to prevent ZenML error


class HuggingFaceProcessorArchiver(Archiver):
    """Archiver for HuggingFace processors and tokenizers.

    Serialization format:
        - Processor/tokenizer config files (preprocessor_config.json, tokenizer.json, etc.)

    Example:
        >>> from transformers import AutoProcessor
        >>> from mindtrace.registry import Registry
        >>>
        >>> processor = AutoProcessor.from_pretrained("google/vit-base-patch16-224")
        >>> registry = Registry()
        >>> registry.save("vit_processor:v1", processor)
        >>> loaded_processor = registry.load("vit_processor:v1")
    """

    ASSOCIATED_TYPES: ClassVar[Tuple[Type[Any], ...]] = _HF_PROCESSOR_TYPES
    ASSOCIATED_ARTIFACT_TYPE: ClassVar[ArtifactType] = ArtifactType.DATA

    def __init__(self, uri: str, **kwargs):
        super().__init__(uri=uri, **kwargs)

    def save(self, processor: Any) -> None:
        """Save the processor/tokenizer to storage.

        Args:
            processor: The processor or tokenizer instance to save.
        """
        if not _HF_AVAILABLE:
            raise ImportError("transformers is not installed")

        os.makedirs(self.uri, exist_ok=True)
        processor.save_pretrained(self.uri)
        self.logger.debug(f"Saved HuggingFace processor to {self.uri}")

    def load(self, data_type: Type[Any]) -> Any:
        """Load the processor/tokenizer from storage.

        Automatically detects whether it's a processor, tokenizer, or feature extractor.

        Args:
            data_type: The expected type.

        Returns:
            The loaded processor/tokenizer instance.
        """
        if not _HF_AVAILABLE:
            raise ImportError("transformers is not installed")

        from transformers import AutoProcessor, AutoTokenizer, AutoImageProcessor

        # Try to load as processor first (most general)
        try:
            processor = AutoProcessor.from_pretrained(self.uri)
            self.logger.debug(f"Loaded HuggingFace processor from {self.uri}")
            return processor
        except Exception:
            pass

        # Try tokenizer
        try:
            tokenizer = AutoTokenizer.from_pretrained(self.uri)
            self.logger.debug(f"Loaded HuggingFace tokenizer from {self.uri}")
            return tokenizer
        except Exception:
            pass

        # Try image processor
        try:
            image_processor = AutoImageProcessor.from_pretrained(self.uri)
            self.logger.debug(f"Loaded HuggingFace image processor from {self.uri}")
            return image_processor
        except Exception as e:
            raise RuntimeError(
                f"Could not load processor/tokenizer from {self.uri}: {e}"
            )


# Register the archiver for processor types
def _register_processor_archivers():
    try:
        from transformers import (
            PreTrainedTokenizerBase,
            ProcessorMixin,
            ImageProcessingMixin,
            FeatureExtractionMixin,
        )

        for processor_type in [
            PreTrainedTokenizerBase,
            ProcessorMixin,
            ImageProcessingMixin,
            FeatureExtractionMixin,
        ]:
            Registry.register_default_materializer(processor_type, HuggingFaceProcessorArchiver)

    except ImportError:
        pass


_register_processor_archivers()

"""Archiver for HuggingFace Transformers models.

Handles saving and loading of:
- All PreTrainedModel subclasses (AutoModelForImageClassification, AutoModelForCausalLM, etc.)
- Associated processors/tokenizers
- PEFT/LoRA adapters
"""

import os
from typing import Any, ClassVar, Tuple, Type

from torch import nn
from zenml.enums import ArtifactType

from mindtrace.registry import Archiver, Registry

# Check if transformers is available
try:
    from transformers import PreTrainedModel
    _HF_AVAILABLE = True
except ImportError:
    _HF_AVAILABLE = False
    PreTrainedModel = None


class HuggingFaceModelArchiver(Archiver):
    """Archiver for HuggingFace Transformers models.

    Serialization format:
        - model files: config.json, pytorch_model.bin or model.safetensors
        - processor files: preprocessor_config.json, tokenizer files (if applicable)
        - adapter/ directory: PEFT adapter config and weights (if applicable)

    Example:
        >>> from transformers import AutoModelForImageClassification
        >>> from mindtrace.registry import Registry
        >>>
        >>> model = AutoModelForImageClassification.from_pretrained("google/vit-base-patch16-224")
        >>> registry = Registry()
        >>> registry.save("vit:v1", model)
        >>> loaded_model = registry.load("vit:v1")
    """

    # HuggingFace models are nn.Module subclasses
    ASSOCIATED_TYPES: ClassVar[Tuple[Type[Any], ...]] = (nn.Module,)
    ASSOCIATED_ARTIFACT_TYPE: ClassVar[ArtifactType] = ArtifactType.MODEL

    def __init__(self, uri: str, **kwargs):
        super().__init__(uri=uri, **kwargs)

    def _is_hf_model(self, model: Any) -> bool:
        """Check if model is a HuggingFace model."""
        if not _HF_AVAILABLE:
            return False
        return isinstance(model, PreTrainedModel)

    def save(self, model: Any) -> None:
        """Save the HuggingFace model to storage.

        Args:
            model: The PreTrainedModel instance to save.
        """
        if not _HF_AVAILABLE:
            raise ImportError("transformers is not installed")

        os.makedirs(self.uri, exist_ok=True)

        # Save the base model
        model.save_pretrained(self.uri)
        self.logger.debug(f"Saved HuggingFace model to {self.uri}")

        # Check for and save PEFT adapter if present
        self._save_peft_adapter(model)

    def _save_peft_adapter(self, model: Any) -> None:
        """Save PEFT adapter if the model has one attached."""
        try:
            import torch
            from peft import PeftModel, get_peft_model_state_dict

            # Check if model is a PeftModel or has peft_config
            if isinstance(model, PeftModel) or hasattr(model, "peft_config"):
                adapter_dir = os.path.join(self.uri, "adapter")
                os.makedirs(adapter_dir, exist_ok=True)

                # Get the peft config
                if hasattr(model, "peft_config"):
                    peft_config = model.peft_config.get("default", None)
                    if peft_config:
                        peft_config.save_pretrained(adapter_dir)

                # Save adapter weights
                adapter_state_dict = get_peft_model_state_dict(model)
                torch.save(adapter_state_dict, os.path.join(adapter_dir, "adapter.bin"))

                self.logger.debug(f"Saved PEFT adapter to {adapter_dir}")

        except ImportError:
            # PEFT not installed, skip adapter saving
            pass
        except Exception as e:
            self.logger.warning(f"Could not save PEFT adapter: {e}")

    def load(self, data_type: Type[Any]) -> Any:
        """Load the HuggingFace model from storage.

        Uses dynamic class detection from config.json to load the correct model type.

        Args:
            data_type: The expected type (PreTrainedModel or subclass).

        Returns:
            The loaded model instance.
        """
        if not _HF_AVAILABLE:
            raise ImportError("transformers is not installed")

        from transformers import AutoConfig

        config_path = os.path.join(self.uri, "config.json")
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"HuggingFace config not found at {config_path}")

        # Load config to determine architecture
        config = AutoConfig.from_pretrained(self.uri)

        # Get the model class from architectures field
        model_cls = self._get_model_class(config)

        # Load the model
        model = model_cls.from_pretrained(self.uri, config=config)
        self.logger.debug(f"Loaded HuggingFace model ({model_cls.__name__}) from {self.uri}")

        # Load PEFT adapter if present
        model = self._load_peft_adapter(model)

        return model

    def _get_model_class(self, config: Any) -> Type[Any]:
        """Determine the model class from config.

        Args:
            config: AutoConfig instance with architecture info.

        Returns:
            The appropriate model class.
        """
        import transformers

        # Try to get class from architectures field
        if hasattr(config, "architectures") and config.architectures:
            arch_name = config.architectures[0]
            try:
                return getattr(transformers, arch_name)
            except AttributeError:
                self.logger.warning(
                    f"Architecture {arch_name} not found in transformers, "
                    "falling back to AutoModel"
                )

        # Fallback to AutoModel
        from transformers import AutoModel
        return AutoModel

    def _load_peft_adapter(self, model: Any) -> Any:
        """Load and attach PEFT adapter if present."""
        adapter_dir = os.path.join(self.uri, "adapter")
        adapter_config_path = os.path.join(adapter_dir, "adapter_config.json")
        adapter_weights_path = os.path.join(adapter_dir, "adapter.bin")

        if not (os.path.exists(adapter_config_path) and os.path.exists(adapter_weights_path)):
            return model

        try:
            import torch
            from peft import PeftConfig, inject_adapter_in_model, set_peft_model_state_dict

            # Load adapter config and inject
            peft_config = PeftConfig.from_pretrained(adapter_dir)
            model = inject_adapter_in_model(peft_config, model)

            # Load adapter weights
            adapter_state = torch.load(adapter_weights_path, map_location="cpu")
            set_peft_model_state_dict(model, adapter_state)

            self.logger.debug(f"Loaded PEFT adapter from {adapter_dir}")

        except ImportError:
            self.logger.warning("PEFT not installed, skipping adapter loading")
        except Exception as e:
            self.logger.warning(f"Could not load PEFT adapter: {e}")

        return model


# Register the archiver - use lazy import to avoid errors if transformers not installed
def _register_hf_archiver():
    try:
        from transformers import PreTrainedModel
        Registry.register_default_materializer(PreTrainedModel, HuggingFaceModelArchiver)
    except ImportError:
        pass


_register_hf_archiver()

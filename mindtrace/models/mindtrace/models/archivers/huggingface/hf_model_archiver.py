"""Archiver for HuggingFace Transformers models.

Handles saving and loading of:
- All PreTrainedModel subclasses (AutoModelForImageClassification, AutoModelForCausalLM, etc.)
- Associated processors/tokenizers
- PEFT/LoRA adapters
"""

import os
from typing import Any, ClassVar, Tuple, Type

from mindtrace.registry import Archiver, Registry
from mindtrace.registry.core.base_materializer import ArtifactType

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

    ASSOCIATED_TYPES: ClassVar[Tuple[Type[Any], ...]] = (PreTrainedModel,) if _HF_AVAILABLE else (object,)
    ASSOCIATED_ARTIFACT_TYPE: ClassVar[ArtifactType] = ArtifactType.MODEL

    def __init__(self, uri: str, **kwargs):
        super().__init__(uri=uri, **kwargs)

    def save(self, model: Any) -> None:
        """Save the HuggingFace model to storage.

        Handles both plain PreTrainedModel and PEFT-wrapped models.
        For PEFT models, merges adapter weights into the base model to produce
        a clean PreTrainedModel state dict, then saves normally.

        Args:
            model: The PreTrainedModel or PeftModel instance to save.
        """
        if not _HF_AVAILABLE:
            raise ImportError("transformers is not installed")

        os.makedirs(self.uri, exist_ok=True)

        if self._is_peft_model(model):
            self._save_peft_model(model)
        else:
            model.save_pretrained(self.uri)
            self.logger.debug(f"Saved HuggingFace model to {self.uri}")
            # Save adapter if a plain PreTrainedModel happens to have one attached
            self._save_peft_adapter(model)

    @staticmethod
    def _is_peft_model(model: Any) -> bool:
        """Check if model is a PEFT-wrapped model without importing peft."""
        return type(model).__module__.startswith("peft.") and hasattr(model, "merge_and_unload")

    def _save_peft_model(self, model: Any) -> None:
        """Save a PEFT-wrapped model by merging adapter into base weights.

        Creates a deep copy, merges adapter weights into the base model,
        and saves the result as a clean PreTrainedModel. The adapter config
        is preserved in a separate directory for provenance.
        """
        import copy
        import json

        from peft import get_peft_model_state_dict

        # Deep copy to avoid mutating the original model
        model_copy = copy.deepcopy(model)
        merged = model_copy.merge_and_unload()
        merged.save_pretrained(self.uri)
        self.logger.debug(f"Saved PeftModel (merged) to {self.uri}")

        # Save adapter config + weights for provenance and potential re-attachment
        adapter_dir = os.path.join(self.uri, "adapter")
        os.makedirs(adapter_dir, exist_ok=True)

        peft_config = model.peft_config.get("default", None)
        if peft_config:
            peft_config.save_pretrained(adapter_dir)

        import torch

        adapter_state_dict = get_peft_model_state_dict(model)
        torch.save(adapter_state_dict, os.path.join(adapter_dir, "adapter.bin"))

        # Mark this as a merged save so the loader knows not to re-apply adapter
        meta_path = os.path.join(adapter_dir, "archiver_meta.json")
        with open(meta_path, "w") as f:
            json.dump({"merged": True, "peft_type": str(peft_config.peft_type) if peft_config else None}, f)

        self.logger.debug(f"Saved PEFT adapter provenance to {adapter_dir}")

    def _save_peft_adapter(self, model: Any) -> None:
        """Save PEFT adapter if the model has one attached.

        Raises:
            ImportError: If model has a PEFT adapter but peft is not installed.
        """
        # Check for adapter without importing peft
        if not (hasattr(model, "peft_config") and model.peft_config):
            return

        try:
            import torch
            from peft import get_peft_model_state_dict
        except ImportError:
            raise ImportError(
                "Model has a PEFT adapter attached but the 'peft' package is not installed. "
                "Install it with: pip install peft"
            )

        adapter_dir = os.path.join(self.uri, "adapter")
        os.makedirs(adapter_dir, exist_ok=True)

        # Save the peft config
        peft_config = model.peft_config.get("default", None)
        if peft_config:
            peft_config.save_pretrained(adapter_dir)

        # Save adapter weights
        adapter_state_dict = get_peft_model_state_dict(model)
        torch.save(adapter_state_dict, os.path.join(adapter_dir, "adapter.bin"))

        self.logger.debug(f"Saved PEFT adapter to {adapter_dir}")

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
                self.logger.warning(f"Architecture {arch_name} not found in transformers, falling back to AutoModel")

        # Fallback to AutoModel
        from transformers import AutoModel

        return AutoModel

    def _load_peft_adapter(self, model: Any) -> Any:
        """Load and attach PEFT adapter if present.

        If the adapter was saved with ``merged=True`` (i.e. the weights were
        already folded into the base model during save), we skip re-injection
        to avoid double-counting the adapter contribution.

        Raises:
            ImportError: If adapter files exist but peft is not installed.
        """
        import json

        adapter_dir = os.path.join(self.uri, "adapter")
        adapter_config_path = os.path.join(adapter_dir, "adapter_config.json")
        adapter_weights_path = os.path.join(adapter_dir, "adapter.bin")

        if not (os.path.exists(adapter_config_path) and os.path.exists(adapter_weights_path)):
            return model

        # Check if adapter weights were already merged into the base model
        meta_path = os.path.join(adapter_dir, "archiver_meta.json")
        if os.path.exists(meta_path):
            with open(meta_path) as f:
                meta = json.load(f)
            if meta.get("merged", False):
                self.logger.debug(f"PEFT adapter at {adapter_dir} was merged during save; skipping re-injection")
                return model

        try:
            import torch
            from peft import PeftConfig, inject_adapter_in_model, set_peft_model_state_dict
        except ImportError:
            raise ImportError(
                f"PEFT adapter found at {adapter_dir} but the 'peft' package is not installed. "
                "Install it with: pip install peft"
            )

        # Load adapter config and inject
        peft_config = PeftConfig.from_pretrained(adapter_dir)
        model = inject_adapter_in_model(peft_config, model)

        # Load adapter weights
        adapter_state = torch.load(adapter_weights_path, map_location="cpu")
        set_peft_model_state_dict(model, adapter_state)

        self.logger.debug(f"Loaded PEFT adapter from {adapter_dir}")

        return model


# Register the archiver - use lazy import to avoid errors if transformers not installed
def _register_hf_archiver():
    try:
        from transformers import PreTrainedModel

        Registry.register_default_materializer(PreTrainedModel, HuggingFaceModelArchiver)
    except ImportError:
        pass

    # Also register PeftModel so PEFT-wrapped models dispatch here
    # instead of falling through to TimmModelArchiver (nn.Module).
    try:
        from peft import PeftModel

        Registry.register_default_materializer(PeftModel, HuggingFaceModelArchiver)
    except ImportError:
        pass


_register_hf_archiver()

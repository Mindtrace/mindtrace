"""Archiver for timm (PyTorch Image Models) models.

Handles saving and loading of timm models with their architecture
configuration and weights.
"""

import json
import os
from typing import Any, ClassVar, Tuple, Type

import torch

# Import timm at module level for ASSOCIATED_TYPES
from torch import nn
from zenml.enums import ArtifactType

from mindtrace.registry import Archiver

try:
    import timm
    _TIMM_AVAILABLE = True
except ImportError:
    _TIMM_AVAILABLE = False


class TimmModelArchiver(Archiver):
    """Archiver for timm (PyTorch Image Models) models.

    Serialization format:
        - config.json: Model configuration (architecture, num_classes, etc.)
        - model.pt: PyTorch state_dict

    Example:
        >>> import timm
        >>> from mindtrace.registry import Registry
        >>>
        >>> model = timm.create_model("resnet50", pretrained=True, num_classes=10)
        >>> registry = Registry()
        >>> registry.save("resnet:v1", model)
        >>> loaded_model = registry.load("resnet:v1")
    """

    # timm models are nn.Module but we identify them via pretrained_cfg attribute
    ASSOCIATED_TYPES: ClassVar[Tuple[Type[Any], ...]] = (nn.Module,)
    ASSOCIATED_ARTIFACT_TYPE: ClassVar[ArtifactType] = ArtifactType.MODEL

    def __init__(self, uri: str, **kwargs):
        super().__init__(uri=uri, **kwargs)

    def _is_timm_model(self, model: Any) -> bool:
        """Check if model is a timm model."""
        if not _TIMM_AVAILABLE:
            return False
        # timm models have pretrained_cfg or default_cfg
        return hasattr(model, "pretrained_cfg") or hasattr(model, "default_cfg")

    def save(self, model: Any) -> None:
        """Save the timm model to storage.

        Args:
            model: The timm model instance to save.
        """
        if not self._is_timm_model(model):
            raise ValueError("Model does not appear to be a timm model")

        os.makedirs(self.uri, exist_ok=True)

        # Extract model configuration
        config = self._extract_config(model)

        # Save config
        config_path = os.path.join(self.uri, "config.json")
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)

        # Save state dict
        model_path = os.path.join(self.uri, "model.pt")
        torch.save(model.state_dict(), model_path)

        self.logger.debug(f"Saved timm model ({config['architecture']}) to {self.uri}")

    def _extract_config(self, model: Any) -> dict:
        """Extract configuration from timm model."""
        config = {}

        # Get architecture name
        if hasattr(model, "pretrained_cfg") and model.pretrained_cfg:
            config["architecture"] = model.pretrained_cfg.get("architecture", "unknown")
            # Store full pretrained_cfg for reference
            config["pretrained_cfg"] = {
                k: v for k, v in model.pretrained_cfg.items()
                if isinstance(v, (str, int, float, bool, list, tuple))
            }
        elif hasattr(model, "default_cfg") and model.default_cfg:
            config["architecture"] = model.default_cfg.get("architecture", "unknown")

        # Get num_classes
        if hasattr(model, "num_classes"):
            config["num_classes"] = model.num_classes

        # Get global_pool if available
        if hasattr(model, "global_pool"):
            pool = model.global_pool
            if hasattr(pool, "pool_type"):
                config["global_pool"] = pool.pool_type
            elif isinstance(pool, str):
                config["global_pool"] = pool

        # Get in_chans if available
        if hasattr(model, "num_features"):
            config["num_features"] = model.num_features

        # Check for drop rate
        if hasattr(model, "drop_rate"):
            config["drop_rate"] = model.drop_rate

        return config

    def load(self, data_type: Type[Any]) -> Any:
        """Load the timm model from storage.

        Args:
            data_type: The expected type.

        Returns:
            The loaded timm model instance.
        """
        if not _TIMM_AVAILABLE:
            raise ImportError("timm is not installed")

        config_path = os.path.join(self.uri, "config.json")
        model_path = os.path.join(self.uri, "model.pt")

        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Config not found at {config_path}")
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Model weights not found at {model_path}")

        # Load config
        with open(config_path, "r") as f:
            config = json.load(f)

        architecture = config.get("architecture")
        if not architecture:
            raise ValueError("No architecture found in config")

        # Build model creation kwargs
        create_kwargs = {
            "pretrained": False,  # We'll load weights manually
        }

        if "num_classes" in config:
            create_kwargs["num_classes"] = config["num_classes"]
        if "global_pool" in config:
            create_kwargs["global_pool"] = config["global_pool"]
        if "drop_rate" in config:
            create_kwargs["drop_rate"] = config["drop_rate"]

        # Create model
        model = timm.create_model(architecture, **create_kwargs)

        # Load state dict
        state_dict = torch.load(model_path, map_location="cpu")
        model.load_state_dict(state_dict)

        self.logger.debug(f"Loaded timm model ({architecture}) from {self.uri}")

        return model


def _register_timm_archiver():
    """Register the timm archiver if timm is available."""
    if not _TIMM_AVAILABLE:
        return

    # We can't easily get a base class for all timm models,
    # so we register a custom type checker
    # For now, users need to import this module to enable timm archiving
    # The archiver will be selected based on _is_timm_model check


_register_timm_archiver()

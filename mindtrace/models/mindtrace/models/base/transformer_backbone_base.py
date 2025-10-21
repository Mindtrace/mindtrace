from abc import ABC, abstractmethod
from typing import Any

import torch


class TransformerBackboneBase(ABC):
    """
    Abstract interface for all backbone models.
    Does NOT inherit from nn.Module.

    Concrete backbones (e.g., ResNetBackbone, DinoV3Backbone)
    will implement this interface and inherit from nn.Module.
    """

    @abstractmethod
    def load_model(self, architecture: str):

        pass

    @abstractmethod
    def get_intermediate_layers(self, x: torch.Tensor, num_layers: int)  -> Any:
        """Return the feature representation for input `x`."""
        pass

    @abstractmethod
    def get_last_self_attention(self, x: torch.Tensor, layer: int) -> Any:
        """ Get the attention weight for a layer"""
        pass


    @abstractmethod
    def plot_attention_map(self, x: torch.Tensor):

        pass



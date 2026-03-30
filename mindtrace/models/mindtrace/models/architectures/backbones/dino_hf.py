"""DINOv2 (with registers) and DINOv3 backbones via HuggingFace ``transformers``.

This module complements the existing ``dino.py`` (which loads DINOv2 via
``torch.hub``) by providing a unified :class:`HuggingFaceDINOBackbone` that
works for **all** DINO variants — including DINOv3 ViT and ConvNeXt families
— through the HuggingFace ``AutoModel`` API.

Registered backbone names
--------------------------

DINOv2 with registers (HuggingFace path):

==================  ========================================  ============
Registry name       HuggingFace model id                      embed_dim
==================  ========================================  ============
dino_v2_small_reg   facebook/dinov2-with-registers-small      384
dino_v2_base_reg    facebook/dinov2-with-registers-base       768
dino_v2_large_reg   facebook/dinov2-with-registers-large      1024
dino_v2_giant_reg   facebook/dinov2-with-registers-giant      1536
==================  ========================================  ============

DINOv3 ViT variants:

====================  ================================================  ============
Registry name         HuggingFace model id                              embed_dim
====================  ================================================  ============
dino_v3_small         facebook/dinov3-vits16-pretrain-lvd1689m          384
dino_v3_small_plus    facebook/dinov3-vits16plus-pretrain-lvd1689m      *
dino_v3_base          facebook/dinov3-vitb16-pretrain-lvd1689m          768
dino_v3_large         facebook/dinov3-vitl16-pretrain-lvd1689m          1024
dino_v3_large_sat     facebook/dinov3-vitl16-pretrain-sat493m           1024
dino_v3_huge_plus     facebook/dinov3-vith16plus-pretrain-lvd1689m      1280
dino_v3_7b            facebook/dinov3-vit7b16-pretrain-lvd1689m         4096
dino_v3_7b_sat        facebook/dinov3-vit7b16-pretrain-sat493m          4096
====================  ================================================  ============

DINOv3 ConvNeXt variants:

==========================  ===================================================  ============
Registry name               HuggingFace model id                                 embed_dim
==========================  ===================================================  ============
dino_v3_convnext_tiny       facebook/dinov3-convnext-tiny-pretrain-lvd1689m      *
dino_v3_convnext_small      facebook/dinov3-convnext-small-pretrain-lvd1689m     *
dino_v3_convnext_base       facebook/dinov3-convnext-base-pretrain-lvd1689m      *
dino_v3_convnext_large      facebook/dinov3-convnext-large-pretrain-lvd1689m     *
==========================  ===================================================  ============

(*) embed_dim is read from ``model.config`` at load time; see :attr:`HuggingFaceDINOBackbone.embed_dim`.

LoRA support
------------

Pass a :class:`LoRAConfig` to any factory or directly to
:class:`HuggingFaceDINOBackbone`::

    from mindtrace.models.architectures.backbones.dino_hf import LoRAConfig
    from mindtrace.models.architectures import build_backbone

    info = build_backbone(
        "dino_v3_large",
        lora_config=LoRAConfig(r=16, target_modules="qkv"),
    )

The backbone module names for LoRA differ between DINOv2 and DINOv3 and are
resolved automatically by :meth:`LoRAConfig.get_target_modules`.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Literal, Optional, Union

import torch
import torch.nn as nn

from mindtrace.models.architectures.backbones.registry import register_backbone

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional dependency guards
# ---------------------------------------------------------------------------

try:
    from transformers import AutoImageProcessor, AutoModel  # noqa: F401

    _HF_AVAILABLE = True
except ImportError:
    _HF_AVAILABLE = False

try:
    from peft import LoraConfig as _PeftLoraConfig  # noqa: F401
    from peft import PeftModel, get_peft_model  # noqa: F401

    _PEFT_AVAILABLE = True
except ImportError:
    _PEFT_AVAILABLE = False


def _require_hf() -> None:
    if not _HF_AVAILABLE:
        raise ImportError(
            "transformers is required for HuggingFace DINO backbones.  Install it with: pip install transformers"
        )


def _require_peft() -> None:
    if not _PEFT_AVAILABLE:
        raise ImportError("peft is required for LoRA support.  Install it with: pip install peft")


# ---------------------------------------------------------------------------
# LoRAConfig
# ---------------------------------------------------------------------------

_TargetModulesPreset = Literal["qv", "qkv", "qkv_proj", "mlp", "all"]

# Attention / MLP module names differ between DINOv2 and DINOv3
_DINOV2_MODULES: dict[str, list[str]] = {
    "qv": ["attention.attention.query", "attention.attention.value"],
    "qkv": ["attention.attention.query", "attention.attention.key", "attention.attention.value"],
    "qkv_proj": [
        "attention.attention.query",
        "attention.attention.key",
        "attention.attention.value",
        "attention.output.dense",
    ],
    "mlp": ["mlp.fc1", "mlp.fc2"],
    "all": [
        "attention.attention.query",
        "attention.attention.key",
        "attention.attention.value",
        "attention.output.dense",
        "mlp.fc1",
        "mlp.fc2",
    ],
}

_DINOV3_MODULES: dict[str, list[str]] = {
    "qv": ["attention.q_proj", "attention.v_proj"],
    "qkv": ["attention.q_proj", "attention.k_proj", "attention.v_proj"],
    "qkv_proj": ["attention.q_proj", "attention.k_proj", "attention.v_proj", "attention.o_proj"],
    "mlp": ["mlp.up_proj", "mlp.down_proj"],
    "all": [
        "attention.q_proj",
        "attention.k_proj",
        "attention.v_proj",
        "attention.o_proj",
        "mlp.up_proj",
        "mlp.down_proj",
    ],
}


@dataclass
class LoRAConfig:
    """LoRA adaptation configuration for HuggingFace DINO backbones.

    Target-module presets follow the LoRA literature for ViT models:

    * ``"qv"``        — Q and V projections (original LoRA paper).
    * ``"qkv"``       — Q, K, V projections (stable, parameter-efficient).
    * ``"qkv_proj"``  — Q, K, V + output projection.
    * ``"mlp"``       — MLP layers only.
    * ``"all"``       — All attention + MLP layers.

    Pass an explicit list of module name substrings to override the preset.

    Args:
        r: LoRA rank.
        lora_alpha: LoRA scaling factor.
        lora_dropout: Dropout probability on LoRA layers.
        target_modules: Preset name or explicit list of module name substrings.
        bias: Which bias parameters to train: ``"none"``, ``"all"``, or
            ``"lora_only"``.
    """

    r: int = 8
    lora_alpha: int = 8
    lora_dropout: float = 0.1
    target_modules: Union[List[str], _TargetModulesPreset] = "qv"
    bias: str = "none"

    def get_target_modules(self, model_name: str) -> List[str]:
        """Resolve the target module list for a given HuggingFace model name.

        Args:
            model_name: HuggingFace model identifier used to distinguish
                DINOv2 (``"dinov2"`` in the name) from DINOv3.

        Returns:
            List of module name substrings for PEFT.
        """
        if isinstance(self.target_modules, list):
            return self.target_modules

        table = _DINOV2_MODULES if "dinov2" in model_name.lower() else _DINOV3_MODULES
        return table.get(self.target_modules, table["qv"])


# ---------------------------------------------------------------------------
# HuggingFaceDINOBackbone
# ---------------------------------------------------------------------------


class _IntermediateOutput:
    """Simple container matching the interface used by MIP heads."""

    def __init__(
        self,
        cls_tokens: tuple[torch.Tensor, ...] | None,
        patch_tokens: tuple[torch.Tensor, ...],
    ) -> None:
        self.cls_tokens = cls_tokens
        self.patch_tokens = patch_tokens


class HuggingFaceDINOBackbone(nn.Module):
    """Unified DINOv2/v3 backbone via HuggingFace ``AutoModel``.

    Handles both ViT-based models (with CLS token + patch tokens + optional
    register tokens) and ConvNeXt-based models (spatial feature maps with
    global pooling as the "CLS" equivalent).

    Args:
        hf_model_name: HuggingFace model identifier, e.g.
            ``"facebook/dinov3-vitl16-pretrain-lvd1689m"``.
        lora_config: Optional :class:`LoRAConfig` for parameter-efficient
            fine-tuning.  Requires ``peft`` to be installed.
        cache_dir: Optional HuggingFace cache directory.
        device: Device string for the model (default ``"cpu"``).
    """

    def __init__(
        self,
        hf_model_name: str,
        lora_config: Optional[LoRAConfig] = None,
        cache_dir: Optional[str] = None,
        device: str = "cpu",
    ) -> None:
        _require_hf()
        super().__init__()

        from transformers import AutoImageProcessor, AutoModel  # noqa: PLC0415

        self.hf_model_name = hf_model_name
        self.lora_enabled = False

        self.processor = AutoImageProcessor.from_pretrained(hf_model_name, use_fast=True, cache_dir=cache_dir)
        self.model = AutoModel.from_pretrained(hf_model_name, cache_dir=cache_dir)

        if lora_config is not None:
            _require_peft()
            from peft import LoraConfig as _PeftCfg  # noqa: PLC0415
            from peft import get_peft_model

            target_mods = lora_config.get_target_modules(hf_model_name)
            peft_cfg = _PeftCfg(
                r=lora_config.r,
                lora_alpha=lora_config.lora_alpha,
                target_modules=target_mods,
                lora_dropout=lora_config.lora_dropout,
                bias=lora_config.bias,
                task_type=None,
            )
            self.model = get_peft_model(self.model, peft_cfg)
            self.lora_enabled = True
            logger.info("LoRA enabled — target modules: %s", target_mods)
            self.print_trainable_parameters()

        # Cache config-derived values
        self._patch_size: int = getattr(self.model.config, "patch_size", 14)
        self._num_register_tokens: int = getattr(self.model.config, "num_register_tokens", 0)

        self.model.to(device)
        self._device = device

    # ------------------------------------------------------------------
    # Architecture detection
    # ------------------------------------------------------------------

    @property
    def is_vit(self) -> bool:
        """``True`` for ViT-based models (have a CLS token); ``False`` for ConvNeXt."""
        cfg = self.model.config
        # ViT configs always have num_attention_heads; ConvNeXt does not.
        return hasattr(cfg, "num_attention_heads")

    # ------------------------------------------------------------------
    # Core properties
    # ------------------------------------------------------------------

    @property
    def embed_dim(self) -> int:
        """Output embedding dimension.

        * ViT: ``config.hidden_size``
        * ConvNeXt: last value of ``config.hidden_sizes``
        """
        cfg = self.model.config
        if self.is_vit:
            return cfg.hidden_size
        # ConvNeXt: hidden_sizes is a list of per-stage channel counts
        if hasattr(cfg, "hidden_sizes"):
            return cfg.hidden_sizes[-1]
        return cfg.hidden_size  # fallback

    @property
    def num_register_tokens(self) -> int:
        """Number of register tokens (0 for models without registers)."""
        return self._num_register_tokens

    @property
    def patch_size(self) -> int:
        """Patch size in pixels."""
        return self._patch_size

    # ------------------------------------------------------------------
    # Forward
    # ------------------------------------------------------------------

    def _forward_raw(self, pixel_values: torch.Tensor) -> Any:
        """Internal: run HF model and return raw ModelOutput. Not part of the public API."""
        return self.model(pixel_values=pixel_values.to(next(self.model.parameters()).device))

    def forward(self, pixel_values: torch.Tensor) -> torch.Tensor:
        """Run backbone and return a ``(B, D)`` feature vector (CLS or pooled token).

        This is the standard ``nn.Module`` forward — compatible with
        :class:`~mindtrace.models.architectures.factory.ModelWrapper` and all
        task heads expecting a 2-D feature tensor.

        For classification heads: use ``model(x)`` directly.
        For segmentation heads:  use :meth:`forward_spatial` or
        :func:`~mindtrace.models.architectures.build_model` with a seg head
        (the factory wires the spatial path automatically).

        Returns:
            ``(B, D)`` tensor — the CLS token for ViT models, the pooled
            output for ConvNeXt models.
        """
        return self.get_cls_tokens(pixel_values)

    def forward_spatial(self, pixel_values: torch.Tensor) -> torch.Tensor:
        """Return patch tokens as a ``(B, D, H_p, W_p)`` spatial feature map.

        Intended for segmentation heads.  ``H_p = H // patch_size``,
        ``W_p = W // patch_size``.  For ConvNeXt models, returns the last
        hidden state permuted to ``(B, C, H, W)`` format.

        Normally you do **not** call this directly — use
        :func:`~mindtrace.models.architectures.build_model` with a seg head
        (``"linear_seg"`` or ``"fpn_seg"``) and the factory wires this path.

        Args:
            pixel_values: ``(B, C, H, W)`` float tensor.

        Returns:
            ``(B, D, H_p, W_p)`` spatial feature map ready for convolutional
            segmentation heads.
        """
        B, C, H, W = pixel_values.shape
        outputs = self._forward_raw(pixel_values)

        if self.is_vit:
            hidden = outputs.last_hidden_state  # (B, 1+reg+N, D)
            start = 1 + self._num_register_tokens
            patches = hidden[:, start:, :]  # (B, N, D)
            H_p = H // self._patch_size
            W_p = W // self._patch_size
            return patches.permute(0, 2, 1).reshape(B, -1, H_p, W_p)
        else:
            # ConvNeXt: last_hidden_state is (B, H_p, W_p, C)
            return outputs.last_hidden_state.permute(0, 3, 1, 2)  # (B, C, H_p, W_p)

    # ------------------------------------------------------------------
    # Feature extraction helpers
    # ------------------------------------------------------------------

    def get_features(self, pixel_values: torch.Tensor) -> tuple[torch.Tensor, Optional[torch.Tensor]]:
        """Return ``(cls_token, patch_tokens)`` from a forward pass.

        For ViT models:
            * ``cls_token``    — ``(B, D)``
            * ``patch_tokens`` — ``(B, N, D)`` where ``N = H_patches × W_patches``

        For ConvNeXt models:
            * ``cls_token``    — ``pooler_output`` ``(B, D)``
            * ``patch_tokens`` — spatial feature map flattened to ``(B, H*W, D)``

        Returns:
            Tuple of ``(cls_token, patch_tokens)``.
        """
        outputs = self._forward_raw(pixel_values)

        if self.is_vit:
            hidden = outputs.last_hidden_state  # (B, 1+registers+N, D)
            cls = hidden[:, 0, :]  # (B, D)
            start = 1 + self._num_register_tokens
            patches = hidden[:, start:, :]  # (B, N, D)
            return cls, patches
        else:
            # ConvNeXt: last_hidden_state is (B, H, W, C) → flatten spatial
            hidden = outputs.last_hidden_state  # (B, H, W, C)
            cls = outputs.pooler_output  # (B, C)
            b, h, w, c = hidden.shape
            patches = hidden.reshape(b, h * w, c)  # (B, H*W, C)
            return cls, patches

    def get_cls_tokens(self, pixel_values: torch.Tensor) -> torch.Tensor:
        """Return the CLS (or pooled) token for each image.

        Args:
            pixel_values: ``(B, C, H, W)`` float tensor.

        Returns:
            ``(B, D)`` feature tensor.
        """
        cls, _ = self.get_features(pixel_values)
        return cls

    def get_patch_tokens(self, pixel_values: torch.Tensor) -> torch.Tensor:
        """Return spatial patch tokens.

        Args:
            pixel_values: ``(B, C, H, W)`` float tensor.

        Returns:
            ``(B, N, D)`` tensor, where ``N = H_patches × W_patches``.
        """
        _, patches = self.get_features(pixel_values)
        return patches

    def get_register_tokens(self, pixel_values: torch.Tensor) -> torch.Tensor:
        """Return register tokens for models that have them.

        Args:
            pixel_values: ``(B, C, H, W)`` float tensor.

        Returns:
            ``(B, num_register_tokens, D)`` tensor.

        Raises:
            ValueError: If this model has no register tokens.
        """
        if self._num_register_tokens == 0:
            raise ValueError(
                f"Model '{self.hf_model_name}' has no register tokens.  Use a DINOv2-with-registers or DINOv3 model."
            )
        outputs = self._forward_raw(pixel_values)
        hidden = outputs.last_hidden_state  # (B, 1+registers+N, D)
        return hidden[:, 1 : 1 + self._num_register_tokens, :]

    def get_intermediate_layers(
        self,
        pixel_values: torch.Tensor,
        n: Union[int, List[int]] = 1,
        return_class_token: bool = True,
    ) -> _IntermediateOutput:
        """Return features from intermediate transformer layers.

        Args:
            pixel_values: ``(B, C, H, W)`` float tensor.
            n: Either the *number* of last layers to return (int) or an
               explicit list of 0-indexed layer indices.
            return_class_token: Whether to include the CLS token in the output.

        Returns:
            :class:`_IntermediateOutput` with:
                * ``cls_tokens``   — tuple of ``(B, D)`` tensors (or ``None``
                  when ``return_class_token=False``).
                * ``patch_tokens`` — tuple of ``(B, N, D)`` tensors.

        Raises:
            ValueError: If called on a ConvNeXt model (no transformer layers).
        """
        if not self.is_vit:
            raise ValueError("get_intermediate_layers is only supported for ViT-based models.")

        outputs = self.model(
            pixel_values=pixel_values.to(next(self.model.parameters()).device),
            output_hidden_states=True,
        )
        hidden_states = outputs.hidden_states  # tuple of (num_layers+1) tensors

        num_layers = len(hidden_states) - 1  # index 0 is the patch embedding
        if isinstance(n, int):
            layer_indices = list(range(max(0, num_layers - n), num_layers))
        else:
            layer_indices = [i + 1 for i in n]  # +1 because [0] is embeddings

        start = 1 + self._num_register_tokens
        cls_list: list[Optional[torch.Tensor]] = []
        patch_list: list[torch.Tensor] = []

        for idx in layer_indices:
            if idx >= len(hidden_states):
                continue
            hs = hidden_states[idx]  # (B, 1+registers+N, D)
            cls_list.append(hs[:, 0, :] if return_class_token else None)
            patch_list.append(hs[:, start:, :])

        cls_out = tuple(cls_list) if return_class_token else None
        return _IntermediateOutput(cls_tokens=cls_out, patch_tokens=tuple(patch_list))

    def get_last_self_attention(
        self,
        pixel_values: torch.Tensor,
    ) -> torch.Tensor:
        """Return attention weights from the last transformer layer.

        Args:
            pixel_values: ``(B, C, H, W)`` float tensor.

        Returns:
            ``(B, num_heads, num_tokens, num_tokens)`` attention weight tensor.
            Falls back to a uniform attention matrix if the model does not
            expose attention weights (e.g. when using a non-eager kernel).

        Raises:
            ValueError: If called on a ConvNeXt model.
        """
        if not self.is_vit:
            raise ValueError("get_last_self_attention is only supported for ViT-based models.")

        dev = next(self.model.parameters()).device
        try:
            # Some models need eager attention to expose weights
            if hasattr(self.model, "set_attn_implementation"):
                try:
                    self.model.set_attn_implementation("eager")
                except Exception:
                    pass

            outputs = self.model(
                pixel_values=pixel_values.to(dev),
                output_attentions=True,
            )
            if hasattr(outputs, "attentions") and outputs.attentions is not None:
                return outputs.attentions[-1]

        except Exception as exc:
            logger.warning("Could not extract attention weights: %s — returning uniform fallback.", exc)

        # Fallback: uniform attention
        cfg = self.model.config
        b = pixel_values.shape[0]
        h_patches = pixel_values.shape[2] // self._patch_size
        w_patches = pixel_values.shape[3] // self._patch_size
        n_tokens = h_patches * w_patches + 1 + self._num_register_tokens
        n_heads = getattr(cfg, "num_attention_heads", 12)
        attn = torch.ones(b, n_heads, n_tokens, n_tokens, device=dev) / n_tokens
        return attn

    # ------------------------------------------------------------------
    # LoRA utilities
    # ------------------------------------------------------------------

    def print_trainable_parameters(self) -> None:
        """Log the number of trainable vs total parameters."""
        if hasattr(self.model, "print_trainable_parameters"):
            self.model.print_trainable_parameters()
        else:
            trainable = sum(p.numel() for p in self.model.parameters() if p.requires_grad)
            total = sum(p.numel() for p in self.model.parameters())
            logger.info("Trainable params: %s / %s  (%.2f%%)", f"{trainable:,}", f"{total:,}", 100 * trainable / total)

    def merge_lora(self) -> None:
        """Merge LoRA adapter weights into the base model and remove adapters.

        After merging, the backbone behaves as a standard model with no LoRA
        overhead.

        Raises:
            ValueError: If LoRA is not enabled.
        """
        if not self.lora_enabled:
            raise ValueError("LoRA is not enabled on this backbone.")
        self.model = self.model.merge_and_unload()
        self.lora_enabled = False
        logger.info("LoRA weights merged into base model.")

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save_pretrained(self, path: str | Path, merge_lora: bool = False) -> None:
        """Save the backbone weights and processor to disk.

        Args:
            path: Directory to save into.
            merge_lora: When ``True`` and LoRA is enabled, merge adapters into
                the base model before saving (produces a larger but standalone
                checkpoint).  When ``False`` (default), only the LoRA adapter
                weights are saved — smaller and suitable for continued training.
        """
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)

        if self.lora_enabled and merge_lora:
            logger.info("Merging LoRA adapters before saving…")
            model_to_save = self.model.merge_and_unload()
            model_to_save.save_pretrained(path)
            lora_state = "merged"
        elif self.lora_enabled:
            self.model.save_pretrained(path)  # PEFT saves adapters only
            lora_state = "lora"
        else:
            self.model.save_pretrained(path)
            lora_state = "none"

        self.processor.save_pretrained(path)

        metadata = {
            "hf_model_name": self.hf_model_name,
            "patch_size": self._patch_size,
            "num_register_tokens": self._num_register_tokens,
            "lora_state": lora_state,
        }
        with open(path / "backbone_metadata.json", "w") as fh:
            json.dump(metadata, fh, indent=2)

        logger.info("Backbone saved to %s", path)

    @classmethod
    def load_pretrained(
        cls,
        path: str | Path,
        device: str = "cpu",
    ) -> "HuggingFaceDINOBackbone":
        """Load a backbone saved with :meth:`save_pretrained`.

        Automatically detects whether the checkpoint contains full weights,
        a merged LoRA, or separate LoRA adapter weights.

        Args:
            path: Directory containing the saved checkpoint.
            device: Device string to load the model onto.

        Returns:
            A fully initialised :class:`HuggingFaceDINOBackbone`.
        """
        _require_hf()
        path = Path(path)

        meta_path = path / "backbone_metadata.json"
        if not meta_path.exists():
            raise ValueError(
                f"No backbone metadata found at {path}.  Was this saved with HuggingFaceDINOBackbone.save_pretrained()?"
            )
        with open(meta_path) as fh:
            meta = json.load(fh)

        from transformers import AutoImageProcessor, AutoModel  # noqa: PLC0415

        instance = object.__new__(cls)
        super(HuggingFaceDINOBackbone, instance).__init__()

        instance.hf_model_name = meta["hf_model_name"]
        instance._patch_size = meta["patch_size"]
        instance._num_register_tokens = meta["num_register_tokens"]
        instance._device = device
        instance.processor = AutoImageProcessor.from_pretrained(path, use_fast=True)

        lora_state = meta.get("lora_state", "none")
        if lora_state == "lora":
            _require_peft()
            from peft import PeftModel  # noqa: PLC0415

            base = AutoModel.from_pretrained(meta["hf_model_name"])
            instance.model = PeftModel.from_pretrained(base, path)
            instance.lora_enabled = True
        else:
            instance.model = AutoModel.from_pretrained(path)
            instance.lora_enabled = False

        instance.model.to(device)
        logger.info("Backbone loaded from %s  (lora_state=%s)", path, lora_state)
        return instance


# ---------------------------------------------------------------------------
# Backbone registry factory + variant table
# ---------------------------------------------------------------------------

# DINOv2-with-registers (HuggingFace path — torch.hub doesn't have these)
_DINOV2_REG_VARIANTS: dict[str, str] = {
    "dino_v2_small_reg": "facebook/dinov2-with-registers-small",
    "dino_v2_base_reg": "facebook/dinov2-with-registers-base",
    "dino_v2_large_reg": "facebook/dinov2-with-registers-large",
    "dino_v2_giant_reg": "facebook/dinov2-with-registers-giant",
}

# DINOv3 ViT variants
_DINOV3_VIT_VARIANTS: dict[str, str] = {
    "dino_v3_small": "facebook/dinov3-vits16-pretrain-lvd1689m",
    "dino_v3_small_plus": "facebook/dinov3-vits16plus-pretrain-lvd1689m",
    "dino_v3_base": "facebook/dinov3-vitb16-pretrain-lvd1689m",
    "dino_v3_large": "facebook/dinov3-vitl16-pretrain-lvd1689m",
    "dino_v3_large_sat": "facebook/dinov3-vitl16-pretrain-sat493m",
    "dino_v3_huge_plus": "facebook/dinov3-vith16plus-pretrain-lvd1689m",
    "dino_v3_7b": "facebook/dinov3-vit7b16-pretrain-lvd1689m",
    "dino_v3_7b_sat": "facebook/dinov3-vit7b16-pretrain-sat493m",
}

# DINOv3 ConvNeXt variants
_DINOV3_CONVNEXT_VARIANTS: dict[str, str] = {
    "dino_v3_convnext_tiny": "facebook/dinov3-convnext-tiny-pretrain-lvd1689m",
    "dino_v3_convnext_small": "facebook/dinov3-convnext-small-pretrain-lvd1689m",
    "dino_v3_convnext_base": "facebook/dinov3-convnext-base-pretrain-lvd1689m",
    "dino_v3_convnext_large": "facebook/dinov3-convnext-large-pretrain-lvd1689m",
}

_ALL_HF_VARIANTS: dict[str, str] = {
    **_DINOV2_REG_VARIANTS,
    **_DINOV3_VIT_VARIANTS,
    **_DINOV3_CONVNEXT_VARIANTS,
}


def _make_hf_dino_factory(hf_model_name: str):
    """Return a backbone-registry-compatible factory for a HuggingFace DINO model.

    The returned factory signature is::

        factory(pretrained=True, lora_config=None, device="cpu", cache_dir=None)
            -> tuple[HuggingFaceDINOBackbone, int]
    """

    def factory(
        pretrained: bool = True,
        lora_config: Optional[LoRAConfig] = None,
        device: str = "cpu",
        cache_dir: Optional[str] = None,
    ) -> tuple["HuggingFaceDINOBackbone", int]:
        """Instantiate a HuggingFace DINO backbone.

        Args:
            pretrained: When ``False`` the model config is loaded but weights
                are randomly initialised (uses ``AutoModel.from_config``).
                Defaults to ``True``.
            lora_config: Optional :class:`LoRAConfig` for LoRA fine-tuning.
            device: Target device string.
            cache_dir: Optional HuggingFace cache directory.

        Returns:
            Tuple of ``(backbone, embed_dim)``.
        """
        if not pretrained:
            from transformers import AutoConfig, AutoModel  # noqa: PLC0415

            cfg = AutoConfig.from_pretrained(hf_model_name, cache_dir=cache_dir)
            model = AutoModel.from_config(cfg)
            # Build a lightweight wrapper to read embed_dim without full loading
            backbone = HuggingFaceDINOBackbone.__new__(HuggingFaceDINOBackbone)
            nn.Module.__init__(backbone)
            from transformers import AutoImageProcessor  # noqa: PLC0415

            backbone.processor = AutoImageProcessor.from_pretrained(hf_model_name, use_fast=True, cache_dir=cache_dir)
            backbone.model = model
            backbone.hf_model_name = hf_model_name
            backbone._patch_size = getattr(cfg, "patch_size", 14)
            backbone._num_register_tokens = getattr(cfg, "num_register_tokens", 0)
            backbone.lora_enabled = False
            backbone._device = device
            backbone.model.to(device)
        else:
            backbone = HuggingFaceDINOBackbone(
                hf_model_name=hf_model_name,
                lora_config=lora_config,
                cache_dir=cache_dir,
                device=device,
            )

        return backbone, backbone.embed_dim

    factory.__name__ = f"_build_hf_{hf_model_name.replace('/', '_').replace('-', '_')}"
    factory.__qualname__ = factory.__name__
    return factory


# Register all variants
for _registry_name, _hf_name in _ALL_HF_VARIANTS.items():
    register_backbone(_registry_name)(_make_hf_dino_factory(_hf_name))

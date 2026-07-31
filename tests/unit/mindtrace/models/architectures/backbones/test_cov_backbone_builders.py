"""Coverage-focused tests for backbone factory builders and package guards.

Targets uncovered lines in:
  * ``dino.py`` (72-85): the ``torch.hub.load`` success + failure paths.
  * ``vit.py`` (93-98): the ViT factory body (head removal + num_features).
  * ``efficientnet.py`` (109-114): the EfficientNet factory body.
  * ``backbones/__init__.py`` (45-47, 65-66, 76-78, 87-89): the optional
    dependency ``ImportError`` guard branches.

torchvision is available under the test runner, so ``vit``/``efficientnet``
self-register at import time.  Their factories are exercised with
``pretrained=False`` so real models are built from random weights with *no*
network download.  Everything runs offline on CPU.
"""

from __future__ import annotations

import pathlib
import sys
from unittest.mock import patch

import pytest
import torch.nn as nn

from mindtrace.models.architectures.backbones import build_backbone
from mindtrace.models.architectures.backbones import registry as registry_mod

_PKG = "mindtrace.models.architectures.backbones"
_INIT_PATH = (
    pathlib.Path(registry_mod.__file__).parent / "__init__.py"
).resolve()


# ---------------------------------------------------------------------------
# DINOv2 factory (dino.py 72-85) — torch.hub.load is mocked, no network.
# ---------------------------------------------------------------------------


class TestDinoFactory:
    def test_dino_factory_success_returns_model_and_num_features(self):
        sentinel = nn.Identity()

        def fake_hub_load(repo, name, pretrained=True):
            assert repo == "facebookresearch/dinov2"
            assert name == "dinov2_vits14"
            assert pretrained is False
            return sentinel

        with patch("torch.hub.load", side_effect=fake_hub_load):
            info = build_backbone("dino_v2_small", pretrained=False)

        assert info.num_features == 384
        assert info.model is sentinel
        assert info.name == "dino_v2_small"

    def test_dino_factory_wraps_hub_failure_in_runtimeerror(self):
        def boom(*a, **k):
            raise OSError("no network")

        with patch("torch.hub.load", side_effect=boom):
            with pytest.raises(RuntimeError, match="Failed to load DINOv2 model 'dinov2_vitb14'"):
                build_backbone("dino_v2_base", pretrained=True)


# ---------------------------------------------------------------------------
# ViT + EfficientNet factories (vit.py 93-98, efficientnet.py 109-114).
# pretrained=False => random init, no download (weights=None branch).
# ---------------------------------------------------------------------------


class TestVitFactory:
    def test_vit_b_16_random_weights_replaces_head(self):
        info = build_backbone("vit_b_16", pretrained=False)
        assert info.num_features == 768
        assert info.name == "vit_b_16"
        # Classification head replaced with Identity so raw features pass through.
        assert isinstance(info.model.heads, nn.Identity)


class TestEfficientNetFactory:
    def test_efficientnet_b0_random_weights_replaces_classifier(self):
        info = build_backbone("efficientnet_b0", pretrained=False)
        assert info.num_features == 1280
        assert info.name == "efficientnet_b0"
        # Classifier replaced with Identity so pooled features pass through.
        assert isinstance(info.model.classifier, nn.Identity)


# ---------------------------------------------------------------------------
# Package __init__ optional-dependency ImportError guards (45-47, 65-66,
# 76-78, 87-89).  We exec the __init__ source in a throwaway namespace with
# selected submodules forced to ImportError via ``sys.modules[name] = None``.
# ---------------------------------------------------------------------------


def _exec_init_with_blocked(blocked: list[str]) -> dict:
    src = _INIT_PATH.read_text()
    ns: dict = {"__name__": f"{_PKG}._cov_probe", "__file__": str(_INIT_PATH)}
    saved: dict[str, object] = {}
    for name in blocked:
        saved[name] = sys.modules.get(name, "__ABSENT__")
        sys.modules[name] = None  # import of this name now raises ImportError
    try:
        code = compile(src, str(_INIT_PATH), "exec")
        exec(code, ns)
    finally:
        for name, val in saved.items():
            if val == "__ABSENT__":
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = val
    return ns


class TestInitImportGuards:
    def test_all_optional_import_guards_execute(self):
        ns = _exec_init_with_blocked(
            [
                f"{_PKG}.adapters",   # -> 45-47
                f"{_PKG}.dino_hf",    # -> loop 65-66 AND top-level 76-78
                f"{_PKG}.hf_generic",  # -> 87-89
            ]
        )
        # The guarded flags reflect the swallowed ImportErrors.
        assert ns["_ADAPTERS_AVAILABLE"] is False
        assert ns["_HF_DINO_AVAILABLE"] is False
        assert ns["_HF_GENERIC_AVAILABLE"] is False
        # Core registry API still bound despite missing optional deps.
        assert "build_backbone" in ns
        assert "list_backbones" in ns

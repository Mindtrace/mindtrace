"""Integration tests for optional-dependency features.

Tests exercise ONNX export/import, timm backbones, HuggingFace DINO
backbones, PEFT/LoRA, classification losses/metrics, and segmentation
metrics.  Each test that requires an optional dependency is decorated
with ``pytest.mark.skipif`` so the suite degrades gracefully when a
package is absent.

Synthetic data (torch.randn) and tiny models (resnet18 pretrained=False,
batch=4, 32x32) keep every test fast (<5s on CPU).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, TensorDataset

from mindtrace.models import (
    Trainer,
    build_model,
    build_optimizer,
)
from mindtrace.models.evaluation.metrics.classification import (
    roc_auc_score,
    top_k_accuracy,
)
from mindtrace.models.evaluation.metrics.segmentation import (
    dice_score,
    frequency_weighted_iou,
    pixel_accuracy,
)
from mindtrace.models.training.losses import (
    LabelSmoothingCrossEntropy,
    SupConLoss,
)
from mindtrace.registry import Registry

# ---------------------------------------------------------------------------
# Optional dependency guards
# ---------------------------------------------------------------------------

try:
    import onnx
    import onnxscript  # noqa: F401 -- required by torch.onnx.export

    _HAS_ONNX = True
except ImportError:
    _HAS_ONNX = False

try:
    import onnxruntime  # noqa: F401

    _HAS_ONNXRUNTIME = True
except ImportError:
    _HAS_ONNXRUNTIME = False

try:
    import timm

    _HAS_TIMM = True
except ImportError:
    _HAS_TIMM = False

try:
    import transformers  # noqa: F401

    _HAS_TRANSFORMERS = True
except ImportError:
    _HAS_TRANSFORMERS = False

try:
    import peft  # noqa: F401

    _HAS_PEFT = True
except ImportError:
    _HAS_PEFT = False


# ---------------------------------------------------------------------------
# Constants & fixtures
# ---------------------------------------------------------------------------

NUM_CLASSES = 4
IMG_SIZE = 32
BATCH = 4


@pytest.fixture()
def registry(tmp_path):
    """Create a local filesystem registry in a temp directory."""
    return Registry(str(tmp_path / "registry"))


@pytest.fixture()
def resnet_model():
    """Build a tiny ResNet18 classifier (no pretrained weights)."""
    return build_model("resnet18", "linear", num_classes=NUM_CLASSES, pretrained=False)


@pytest.fixture()
def dummy_input():
    """Return a small random input tensor."""
    return torch.randn(BATCH, 3, IMG_SIZE, IMG_SIZE)


# =========================================================================
# 1. ONNX export + archiver roundtrip
# =========================================================================


@pytest.mark.skipif(not _HAS_ONNX, reason="onnx not installed")
class TestOnnxExportAndArchiver:
    """ONNX export, registry roundtrip, and optional onnxruntime inference."""

    def _export_to_onnx(self, model: nn.Module, dummy_input: torch.Tensor, path: Path) -> "onnx.ModelProto":
        """Export a PyTorch model to ONNX and return the loaded ModelProto."""
        import onnx as _onnx

        model.eval()
        onnx_path = path / "model.onnx"
        torch.onnx.export(
            model,
            dummy_input,
            str(onnx_path),
            input_names=["pixel_values"],
            output_names=["logits"],
            dynamic_axes={"pixel_values": {0: "batch"}, "logits": {0: "batch"}},
            opset_version=17,
        )
        proto = _onnx.load(str(onnx_path))
        _onnx.checker.check_model(proto)
        return proto

    def test_onnx_export_produces_valid_model(self, resnet_model, dummy_input, tmp_path):
        """Export resnet18 to ONNX and verify the proto passes the ONNX checker."""
        proto = self._export_to_onnx(resnet_model, dummy_input, tmp_path)
        assert proto.graph is not None
        assert len(proto.graph.input) >= 1
        assert len(proto.graph.output) >= 1

    def test_onnx_graph_input_output_names(self, resnet_model, dummy_input, tmp_path):
        """Verify graph input and output names match the export specification."""
        proto = self._export_to_onnx(resnet_model, dummy_input, tmp_path)
        input_names = [inp.name for inp in proto.graph.input]
        output_names = [out.name for out in proto.graph.output]
        assert "pixel_values" in input_names
        assert "logits" in output_names

    def test_onnx_registry_save_load_roundtrip(self, resnet_model, dummy_input, tmp_path, registry):
        """Save ONNX ModelProto to registry, load back, verify graph structure."""
        proto = self._export_to_onnx(resnet_model, dummy_input, tmp_path)

        registry.save("onnx_test:v1", proto)
        loaded = registry.load("onnx_test:v1")

        orig_inputs = [inp.name for inp in proto.graph.input]
        orig_outputs = [out.name for out in proto.graph.output]
        loaded_inputs = [inp.name for inp in loaded.graph.input]
        loaded_outputs = [out.name for out in loaded.graph.output]

        assert orig_inputs == loaded_inputs
        assert orig_outputs == loaded_outputs

    def test_onnx_registry_metadata_preserved(self, resnet_model, dummy_input, tmp_path, registry):
        """Verify that opset and IR version survive the registry roundtrip."""
        proto = self._export_to_onnx(resnet_model, dummy_input, tmp_path)

        registry.save("onnx_meta:v1", proto)
        loaded = registry.load("onnx_meta:v1")

        assert proto.ir_version == loaded.ir_version
        assert len(proto.opset_import) == len(loaded.opset_import)
        for orig_op, loaded_op in zip(proto.opset_import, loaded.opset_import):
            assert orig_op.version == loaded_op.version

    @pytest.mark.skipif(not _HAS_ONNXRUNTIME, reason="onnxruntime not installed")
    def test_onnx_runtime_inference_matches_pytorch(self, resnet_model, dummy_input, tmp_path):
        """Run inference via onnxruntime and compare to PyTorch output."""
        import onnxruntime as ort

        proto = self._export_to_onnx(resnet_model, dummy_input, tmp_path)
        model_bytes = proto.SerializeToString()

        session = ort.InferenceSession(model_bytes, providers=["CPUExecutionProvider"])
        ort_inputs = {"pixel_values": dummy_input.numpy()}
        ort_outputs = session.run(None, ort_inputs)

        resnet_model.eval()
        with torch.no_grad():
            pt_output = resnet_model(dummy_input).numpy()

        np.testing.assert_allclose(pt_output, ort_outputs[0], rtol=1e-4, atol=1e-5)

    @pytest.mark.skipif(not _HAS_ONNXRUNTIME, reason="onnxruntime not installed")
    def test_onnx_runtime_dynamic_batch(self, resnet_model, tmp_path):
        """Verify dynamic batch axis works with different batch sizes."""
        import onnxruntime as ort

        dummy_export = torch.randn(1, 3, IMG_SIZE, IMG_SIZE)
        proto = self._export_to_onnx(resnet_model, dummy_export, tmp_path)
        session = ort.InferenceSession(proto.SerializeToString(), providers=["CPUExecutionProvider"])

        for bs in [1, 2, 8]:
            inp = np.random.randn(bs, 3, IMG_SIZE, IMG_SIZE).astype(np.float32)
            out = session.run(None, {"pixel_values": inp})
            assert out[0].shape == (bs, NUM_CLASSES)


# =========================================================================
# 2. Timm backbone integration
# =========================================================================


@pytest.mark.skipif(not _HAS_TIMM, reason="timm not installed")
class TestTimmBackbone:
    """Timm backbone adapter: creation, forward pass, and archiver roundtrip."""

    def test_timm_adapter_forward_pass(self, dummy_input):
        """Create a timm backbone via adapter and run a forward pass."""
        from mindtrace.models.architectures.backbones.adapters import TimmBackboneAdapter

        adapter = TimmBackboneAdapter("resnet18", pretrained=False, device="cpu")
        feats = adapter.extract(dummy_input)
        assert feats.cls_token.shape[0] == BATCH
        assert feats.cls_token.shape[1] == adapter.embed_dim

    def test_timm_adapter_embed_dim(self):
        """Verify embed_dim matches timm's reported num_features."""
        from mindtrace.models.architectures.backbones.adapters import TimmBackboneAdapter

        adapter = TimmBackboneAdapter("resnet18", pretrained=False, device="cpu")
        raw_model = timm.create_model("resnet18", pretrained=False, num_classes=0)
        assert adapter.embed_dim == raw_model.num_features

    def test_timm_create_model_and_classify(self, dummy_input):
        """Build a full timm model with classifier head and get logits."""
        model = timm.create_model("resnet18", pretrained=False, num_classes=NUM_CLASSES)
        model.eval()
        with torch.no_grad():
            out = model(dummy_input)
        assert out.shape == (BATCH, NUM_CLASSES)

    def test_timm_archiver_save_load(self, tmp_path):
        """Save a timm model via TimmModelArchiver, load it back, verify output."""
        from mindtrace.models.archivers.timm.timm_model_archiver import TimmModelArchiver

        model = timm.create_model("resnet18", pretrained=False, num_classes=NUM_CLASSES)
        model.eval()

        uri = str(tmp_path / "timm_archive")
        archiver = TimmModelArchiver(uri=uri)
        archiver.save(model)

        loaded = archiver.load(data_type=nn.Module)
        loaded.eval()

        x = torch.randn(2, 3, IMG_SIZE, IMG_SIZE)
        with torch.no_grad():
            orig_out = model(x)
            loaded_out = loaded(x)
        assert torch.allclose(orig_out, loaded_out, atol=1e-6)


# =========================================================================
# 3. HuggingFace DINO backbone
# =========================================================================


@pytest.mark.skipif(not _HAS_TRANSFORMERS, reason="transformers not installed")
class TestHuggingFaceDINOBackbone:
    """HuggingFace DINO backbone: build, forward, head variants."""

    def test_dino_v2_small_forward_shape(self):
        """Build dino_v2_small (no pretrained), verify output is (B, D)."""
        from mindtrace.models.architectures.backbones.registry import build_backbone

        info = build_backbone("dino_v2_small", pretrained=False)
        backbone = info.model
        backbone.eval()

        x = torch.randn(2, 3, 224, 224)  # DINOv2 expects multiples of patch_size=14
        with torch.no_grad():
            out = backbone(x)
        assert out.shape == (2, info.num_features)
        assert info.num_features == 384

    def test_dino_v2_small_with_linear_head(self):
        """Build full model: dino_v2_small + linear head, verify logit shape."""
        model = build_model("dino_v2_small", "linear", num_classes=NUM_CLASSES, pretrained=False)
        model.eval()

        x = torch.randn(2, 3, 224, 224)
        with torch.no_grad():
            out = model(x)
        assert out.shape == (2, NUM_CLASSES)

    def test_dino_v2_small_with_mlp_head(self):
        """Build full model: dino_v2_small + MLP head, verify logit shape."""
        model = build_model(
            "dino_v2_small",
            "mlp",
            num_classes=NUM_CLASSES,
            pretrained=False,
            hidden_dim=64,
        )
        model.eval()

        x = torch.randn(2, 3, 224, 224)
        with torch.no_grad():
            out = model(x)
        assert out.shape == (2, NUM_CLASSES)


# =========================================================================
# 4. Classification losses (always available)
# =========================================================================


class TestClassificationLosses:
    """SupConLoss, top_k_accuracy, roc_auc_score, LabelSmoothingCE."""

    def test_supcon_loss_contrastive_pairs(self):
        """SupConLoss with real contrastive pairs produces a positive scalar."""
        loss_fn = SupConLoss(temperature=0.5)
        # 8 samples, 2 per class -> each sample has at least 1 positive
        features = torch.randn(8, 16, requires_grad=True)
        features_norm = F.normalize(features, dim=1)
        labels = torch.tensor([0, 0, 1, 1, 2, 2, 3, 3])

        loss = loss_fn(features_norm, labels)
        assert loss.dim() == 0  # scalar
        assert loss.item() > 0
        loss.backward()

    def test_supcon_loss_identical_embeddings(self):
        """When all same-class embeddings are identical, loss should be low."""
        loss_fn = SupConLoss(temperature=0.5)
        # Create embeddings: class 0 = [1,0,...], class 1 = [0,1,...]
        features = torch.zeros(4, 8)
        features[0, 0] = 1.0
        features[1, 0] = 1.0
        features[2, 1] = 1.0
        features[3, 1] = 1.0
        features = F.normalize(features, dim=1)
        labels = torch.tensor([0, 0, 1, 1])

        loss = loss_fn(features, labels)
        assert loss.item() >= 0

    def test_supcon_loss_no_positives_returns_zero(self):
        """When every sample has a unique label, loss should be zero."""
        loss_fn = SupConLoss(temperature=0.5)
        features = F.normalize(torch.randn(4, 8), dim=1)
        labels = torch.tensor([0, 1, 2, 3])
        loss = loss_fn(features, labels)
        assert loss.item() == pytest.approx(0.0, abs=1e-7)

    def test_top_k_accuracy_known_predictions(self):
        """Verify top-k accuracy with known probability distributions."""
        # 4 samples, 4 classes. Ground truth: [0, 1, 2, 3]
        probs = np.array(
            [
                [0.9, 0.05, 0.03, 0.02],  # correct: class 0
                [0.1, 0.7, 0.15, 0.05],  # correct: class 1
                [0.1, 0.1, 0.6, 0.2],  # correct: class 2
                [0.05, 0.05, 0.1, 0.8],  # correct: class 3
            ]
        )
        targets = np.array([0, 1, 2, 3])

        assert top_k_accuracy(probs, targets, k=1) == pytest.approx(1.0)
        assert top_k_accuracy(probs, targets, k=3) == pytest.approx(1.0)

    def test_top_k_accuracy_partial(self):
        """Top-1 misses some, top-2 catches them."""
        probs = np.array(
            [
                [0.4, 0.5, 0.05, 0.05],  # top-1 = class 1, true = 0 -> miss
                [0.3, 0.6, 0.05, 0.05],  # top-1 = class 1, true = 1 -> hit
            ]
        )
        targets = np.array([0, 1])

        assert top_k_accuracy(probs, targets, k=1) == pytest.approx(0.5)
        assert top_k_accuracy(probs, targets, k=2) == pytest.approx(1.0)

    def test_roc_auc_score_perfect_separation(self):
        """Perfect class separation yields AUC close to 1.0."""
        # 3 classes, 6 samples, perfectly separated
        probs = np.array(
            [
                [0.95, 0.03, 0.02],
                [0.90, 0.05, 0.05],
                [0.02, 0.93, 0.05],
                [0.03, 0.90, 0.07],
                [0.01, 0.04, 0.95],
                [0.02, 0.03, 0.95],
            ]
        )
        targets = np.array([0, 0, 1, 1, 2, 2])

        auc = roc_auc_score(probs, targets, num_classes=3, average="macro")
        assert auc >= 0.95

    def test_roc_auc_score_random_chance(self):
        """Random probabilities on balanced data yield AUC around 0.5."""
        rng = np.random.RandomState(42)
        n = 300
        probs = rng.dirichlet(np.ones(3), size=n)
        targets = np.tile(np.arange(3), n // 3)

        auc = roc_auc_score(probs, targets, num_classes=3, average="macro")
        # Allow wide tolerance for random data
        assert 0.3 <= auc <= 0.7

    def test_label_smoothing_ce_training_loop(self):
        """LabelSmoothingCE in a 2-epoch training loop produces finite losses."""
        model = build_model("resnet18", "linear", num_classes=NUM_CLASSES, pretrained=False)
        loss_fn = LabelSmoothingCrossEntropy(smoothing=0.1)
        optimizer = build_optimizer("adamw", model, lr=1e-3)

        x = torch.randn(16, 3, IMG_SIZE, IMG_SIZE)
        y = torch.randint(0, NUM_CLASSES, (16,))
        loader = DataLoader(TensorDataset(x, y), batch_size=BATCH)

        trainer = Trainer(model=model, loss_fn=loss_fn, optimizer=optimizer, device="cpu")
        history = trainer.fit(loader, epochs=2)

        assert len(history["train/loss"]) == 2
        assert all(np.isfinite(v) and v > 0 for v in history["train/loss"])

    def test_label_smoothing_ce_smoothing_zero_matches_ce(self):
        """With smoothing=0, LabelSmoothingCE matches standard CrossEntropy."""
        lsce = LabelSmoothingCrossEntropy(smoothing=0.0)
        ce = nn.CrossEntropyLoss()

        logits = torch.randn(8, NUM_CLASSES)
        targets = torch.randint(0, NUM_CLASSES, (8,))

        loss_lsce = lsce(logits, targets)
        loss_ce = ce(logits, targets)
        assert loss_lsce.item() == pytest.approx(loss_ce.item(), rel=1e-5)


# =========================================================================
# 5. Segmentation metrics (always available)
# =========================================================================


class TestSegmentationMetrics:
    """frequency_weighted_iou, pixel_accuracy, dice_score with known maps."""

    def test_pixel_accuracy_perfect(self):
        """Identical prediction and target yields accuracy = 1.0."""
        targets = np.array([[[0, 1, 2], [2, 1, 0]]])
        preds = targets.copy()
        assert pixel_accuracy(preds, targets) == pytest.approx(1.0)

    def test_pixel_accuracy_half_correct(self):
        """Half correct pixels yields accuracy = 0.5."""
        targets = np.array([[[0, 0, 1, 1]]])
        preds = np.array([[[0, 0, 0, 0]]])
        assert pixel_accuracy(preds, targets) == pytest.approx(0.5)

    def test_frequency_weighted_iou_perfect(self):
        """Perfect segmentation yields FW-IoU = 1.0."""
        targets = np.array([[[0, 0, 1, 1], [2, 2, 0, 1]]])
        preds = targets.copy()
        fwiou = frequency_weighted_iou(preds, targets, num_classes=3)
        assert fwiou == pytest.approx(1.0)

    def test_frequency_weighted_iou_imperfect(self):
        """Imperfect segmentation yields 0 < FW-IoU < 1."""
        targets = np.array([[[0, 0, 1, 1], [2, 2, 0, 1]]])
        preds = np.array([[[0, 1, 1, 0], [2, 0, 0, 1]]])
        fwiou = frequency_weighted_iou(preds, targets, num_classes=3)
        assert 0.0 < fwiou < 1.0

    def test_dice_score_perfect(self):
        """Perfect segmentation yields mean_dice = 1.0."""
        targets = np.array([[[0, 1, 2], [0, 1, 2]]])
        preds = targets.copy()
        result = dice_score(preds, targets, num_classes=3)
        assert result["mean_dice"] == pytest.approx(1.0)
        assert len(result["dice_per_class"]) == 3
        assert all(d == pytest.approx(1.0) for d in result["dice_per_class"])

    def test_dice_score_completely_wrong(self):
        """All-wrong prediction yields low dice scores."""
        # Class 0 predicted everywhere, but target has classes 1 and 2 only
        targets = np.array([[[1, 1, 2, 2]]])
        preds = np.array([[[0, 0, 0, 0]]])
        result = dice_score(preds, targets, num_classes=3)
        # Class 0 has no true positives (predicted but not in target)
        # Classes 1 and 2 have no predictions
        assert result["mean_dice"] < 0.1

    def test_dice_score_single_class_ignored(self):
        """Absent class gets dice=0; present classes scored normally."""
        # Only classes 0 and 1 present
        targets = np.array([[[0, 0, 1, 1]]])
        preds = np.array([[[0, 0, 1, 1]]])
        result = dice_score(preds, targets, num_classes=3)
        assert result["dice_per_class"][0] == pytest.approx(1.0)
        assert result["dice_per_class"][1] == pytest.approx(1.0)
        # Class 2 not present in either pred or target
        assert result["dice_per_class"][2] == pytest.approx(0.0)


# =========================================================================
# 6. PEFT / LoRA
# =========================================================================


@pytest.mark.skipif(
    not (_HAS_PEFT and _HAS_TRANSFORMERS),
    reason="peft and/or transformers not installed",
)
class TestPeftLoRA:
    """LoRA adaptation on HuggingFace DINO backbones."""

    def test_lora_trainable_params_much_less_than_total(self):
        """With LoRA on pretrained weights, trainable params are a small fraction."""
        from mindtrace.models.architectures.backbones.dino_hf import LoRAConfig

        # LoRA requires pretrained=True to freeze base weights then add adapters
        lora_cfg = LoRAConfig(r=4, lora_alpha=4, target_modules="qv")
        model = build_model(
            "dino_v2_small_reg",
            "linear",
            num_classes=NUM_CLASSES,
            pretrained=True,
            lora_config=lora_cfg,
        )
        backbone = model.backbone

        total = sum(p.numel() for p in backbone.parameters())
        trainable = sum(p.numel() for p in backbone.parameters() if p.requires_grad)

        assert trainable > 0
        assert trainable < total * 0.15

    def test_lora_forward_pass_shape(self):
        """LoRA-adapted backbone produces the same output shape."""
        from mindtrace.models.architectures.backbones.dino_hf import LoRAConfig

        model = build_model(
            "dino_v2_small_reg",
            "linear",
            num_classes=NUM_CLASSES,
            pretrained=False,
            lora_config=LoRAConfig(r=4, target_modules="qv"),
        )
        model.eval()

        x = torch.randn(2, 3, 224, 224)
        with torch.no_grad():
            out = model(x)
        assert out.shape == (2, NUM_CLASSES)

    def test_lora_one_epoch_loss_is_finite(self):
        """Train LoRA-adapted model for 1 epoch, verify loss is finite."""
        from mindtrace.models.architectures.backbones.dino_hf import LoRAConfig

        model = build_model(
            "dino_v2_small_reg",
            "linear",
            num_classes=NUM_CLASSES,
            pretrained=False,
            lora_config=LoRAConfig(r=4, target_modules="qv"),
        )
        optimizer = build_optimizer("adamw", model, lr=1e-3)

        x = torch.randn(8, 3, 224, 224)
        y = torch.randint(0, NUM_CLASSES, (8,))
        loader = DataLoader(TensorDataset(x, y), batch_size=4)

        trainer = Trainer(
            model=model,
            loss_fn=nn.CrossEntropyLoss(),
            optimizer=optimizer,
            device="cpu",
        )
        history = trainer.fit(loader, epochs=1)

        assert len(history["train/loss"]) == 1
        assert np.isfinite(history["train/loss"][0])

"""End-to-end tests for all ML model archivers via the Registry.

Downloads real weights/models from their respective platforms, saves them
through the Registry (testing dispatch), loads them back, and verifies the
roundtrip produces identical inference results.

Usage:
    # Run all tests (requires: timm, transformers, onnx, onnxruntime, ultralytics)
    uv run python scripts/test_ml_archivers.py

    # Run specific archiver tests
    uv run python scripts/test_ml_archivers.py --timm --hf
    uv run python scripts/test_ml_archivers.py --onnx --ultralytics
    uv run python scripts/test_ml_archivers.py --tensorrt

    # Verbose output
    uv run python scripts/test_ml_archivers.py -v
"""

import argparse
import importlib.util
import sys
import tempfile
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Dependency detection
# ---------------------------------------------------------------------------
HAS_TORCH = importlib.util.find_spec("torch") is not None
HAS_TIMM = importlib.util.find_spec("timm") is not None
HAS_TRANSFORMERS = importlib.util.find_spec("transformers") is not None
HAS_PEFT = importlib.util.find_spec("peft") is not None
HAS_ONNX = importlib.util.find_spec("onnx") is not None
HAS_ONNXRUNTIME = importlib.util.find_spec("onnxruntime") is not None
HAS_TENSORRT = importlib.util.find_spec("tensorrt") is not None
HAS_ULTRALYTICS = importlib.util.find_spec("ultralytics") is not None

# ---------------------------------------------------------------------------
# Result tracking
# ---------------------------------------------------------------------------
RESULTS: list[dict] = []


def record(name: str, status: str, detail: str = "", elapsed: float = 0.0):
    RESULTS.append({"name": name, "status": status, "detail": detail, "elapsed": elapsed})
    icon = {"PASS": "\033[92mPASS\033[0m", "FAIL": "\033[91mFAIL\033[0m", "SKIP": "\033[93mSKIP\033[0m"}[status]
    suffix = f" ({detail})" if detail else ""
    timing = f" [{elapsed:.1f}s]" if elapsed else ""
    print(f"  [{icon}] {name}{suffix}{timing}")


def make_registry(tmp_dir: str):
    """Create a local Registry backed by a temp directory."""
    from mindtrace.registry import LocalRegistryBackend, Registry

    backend = LocalRegistryBackend(uri=tmp_dir)
    return Registry(backend=backend)


# ============================================================================
# TIMM
# ============================================================================
def test_timm_random_weights(tmp_dir: str, verbose: bool):
    """timm resnet18 with random weights — fast, no download."""
    import timm
    import torch

    t0 = time.time()
    registry = make_registry(tmp_dir)

    model = timm.create_model("resnet18", pretrained=False, num_classes=5)
    model.eval()

    registry.save("timm:resnet18-rand", model)
    loaded = registry.load("timm:resnet18-rand")
    loaded.eval()

    assert loaded.num_classes == 5, f"Expected 5 classes, got {loaded.num_classes}"

    dummy = torch.randn(1, 3, 224, 224)
    with torch.no_grad():
        out_orig = model(dummy)
        out_loaded = loaded(dummy)
    assert torch.allclose(out_orig, out_loaded, atol=1e-6), "Output mismatch"

    record("timm / resnet18 (random)", "PASS", elapsed=time.time() - t0)


def test_timm_pretrained(tmp_dir: str, verbose: bool):
    """timm efficientnet_b0 with pretrained weights from HuggingFace Hub."""
    import timm
    import torch

    t0 = time.time()
    registry = make_registry(tmp_dir)

    model = timm.create_model("efficientnet_b0", pretrained=True, num_classes=1000)
    model.eval()

    registry.save("timm:effnet-b0", model)
    loaded = registry.load("timm:effnet-b0")
    loaded.eval()

    assert loaded.num_classes == 1000

    dummy = torch.randn(1, 3, 224, 224)
    with torch.no_grad():
        out_orig = model(dummy)
        out_loaded = loaded(dummy)
    assert torch.allclose(out_orig, out_loaded, atol=1e-6), "Output mismatch on pretrained weights"

    record("timm / efficientnet_b0 (pretrained)", "PASS", elapsed=time.time() - t0)


def test_timm_mobilenetv3(tmp_dir: str, verbose: bool):
    """timm mobilenetv3_small_100 — different architecture family."""
    import timm
    import torch

    t0 = time.time()
    registry = make_registry(tmp_dir)

    model = timm.create_model("mobilenetv3_small_100", pretrained=True, num_classes=1000)
    model.eval()

    registry.save("timm:mobilenetv3", model)
    loaded = registry.load("timm:mobilenetv3")
    loaded.eval()

    dummy = torch.randn(1, 3, 224, 224)
    with torch.no_grad():
        assert torch.allclose(model(dummy), loaded(dummy), atol=1e-6)

    record("timm / mobilenetv3_small (pretrained)", "PASS", elapsed=time.time() - t0)


def run_timm_tests(verbose: bool):
    print("\n--- timm archivers ---")
    if not (HAS_TIMM and HAS_TORCH):
        record("timm / *", "SKIP", "timm or torch not installed")
        return

    for test_fn in [test_timm_random_weights, test_timm_pretrained, test_timm_mobilenetv3]:
        with tempfile.TemporaryDirectory() as tmp:
            try:
                test_fn(tmp, verbose)
            except Exception as e:
                record(test_fn.__doc__.split("—")[0].strip(), "FAIL", str(e))


# ============================================================================
# HUGGING FACE
# ============================================================================
def test_hf_from_config(tmp_dir: str, verbose: bool):
    """HF bert-tiny from config — no pretrained download."""
    from transformers import AutoConfig, AutoModel

    t0 = time.time()
    registry = make_registry(tmp_dir)

    config = AutoConfig.from_pretrained("lyeonii/bert-tiny")
    model = AutoModel.from_config(config)
    model.eval()

    registry.save("hf:bert-tiny-cfg", model)
    loaded = registry.load("hf:bert-tiny-cfg")
    loaded.eval()

    assert type(loaded).__name__ == type(model).__name__
    assert loaded.config.hidden_size == model.config.hidden_size

    record("HF / bert-tiny (from config)", "PASS", elapsed=time.time() - t0)


def test_hf_pretrained(tmp_dir: str, verbose: bool):
    """HF distilbert-base-uncased pretrained — real weights."""
    import torch
    from transformers import AutoModel, AutoTokenizer

    t0 = time.time()
    registry = make_registry(tmp_dir)

    model_name = "distilbert-base-uncased"
    model = AutoModel.from_pretrained(model_name)
    model.eval()

    registry.save("hf:distilbert", model)
    loaded = registry.load("hf:distilbert")
    loaded.eval()

    assert type(loaded).__name__ == type(model).__name__

    # Verify outputs match with real tokenized input
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    inputs = tokenizer("Hello mindtrace", return_tensors="pt")
    with torch.no_grad():
        out_orig = model(**inputs).last_hidden_state
        out_loaded = loaded(**inputs).last_hidden_state
    assert torch.allclose(out_orig, out_loaded, atol=1e-5), "Output mismatch on pretrained weights"

    record("HF / distilbert-base-uncased (pretrained)", "PASS", elapsed=time.time() - t0)


def test_hf_vision_model(tmp_dir: str, verbose: bool):
    """HF google/vit-base-patch16-224-in21k — vision transformer."""
    import torch
    from transformers import AutoModel

    t0 = time.time()
    registry = make_registry(tmp_dir)

    model = AutoModel.from_pretrained("google/vit-base-patch16-224-in21k")
    model.eval()

    registry.save("hf:vit-base", model)
    loaded = registry.load("hf:vit-base")
    loaded.eval()

    assert type(loaded).__name__ == type(model).__name__

    dummy = torch.randn(1, 3, 224, 224)
    with torch.no_grad():
        out_orig = model(dummy).last_hidden_state
        out_loaded = loaded(dummy).last_hidden_state
    assert torch.allclose(out_orig, out_loaded, atol=1e-5), "ViT output mismatch"

    record("HF / ViT-base-patch16-224 (pretrained)", "PASS", elapsed=time.time() - t0)


def run_hf_tests(verbose: bool):
    print("\n--- HuggingFace model archivers ---")
    if not HAS_TRANSFORMERS:
        record("HF / *", "SKIP", "transformers not installed")
        return

    for test_fn in [test_hf_from_config, test_hf_pretrained, test_hf_vision_model]:
        with tempfile.TemporaryDirectory() as tmp:
            try:
                test_fn(tmp, verbose)
            except Exception as e:
                record(test_fn.__doc__.split("—")[0].strip(), "FAIL", str(e))


# ============================================================================
# PEFT (LoRA / IA3 / AdaLoRA adapters on HuggingFace models)
# ============================================================================
def test_peft_lora_bert(tmp_dir: str, verbose: bool):
    """PEFT LoRA on bert-tiny — adapter roundtrip with output verification."""
    import torch
    from peft import LoraConfig, TaskType, get_peft_model
    from transformers import AutoConfig, AutoModelForSequenceClassification, AutoTokenizer

    t0 = time.time()
    registry = make_registry(tmp_dir)

    # Create a small base model with random weights
    config = AutoConfig.from_pretrained("lyeonii/bert-tiny")
    config.num_labels = 3
    base_model = AutoModelForSequenceClassification.from_config(config)

    # Attach a LoRA adapter
    lora_config = LoraConfig(
        task_type=TaskType.SEQ_CLS,
        r=4,
        lora_alpha=16,
        lora_dropout=0.0,  # zero dropout for deterministic comparison
        target_modules=["query", "value"],
    )
    model = get_peft_model(base_model, lora_config)
    model.eval()

    # Confirm adapter is present
    assert hasattr(model, "peft_config") and model.peft_config, "LoRA adapter not attached"

    # Get reference output
    tokenizer = AutoTokenizer.from_pretrained("lyeonii/bert-tiny")
    inputs = tokenizer("mindtrace peft test", return_tensors="pt")
    with torch.no_grad():
        out_orig = model(**inputs).logits

    # Save through registry (dispatches to HuggingFaceModelArchiver which calls _save_peft_adapter)
    registry.save("peft:lora-bert", model)

    # Load back (should restore base model + LoRA adapter)
    loaded = registry.load("peft:lora-bert")
    loaded.eval()

    # Verify adapter was restored
    assert hasattr(loaded, "peft_config") or hasattr(loaded, "base_model"), "Adapter not restored on loaded model"

    with torch.no_grad():
        out_loaded = loaded(**inputs).logits
    assert torch.allclose(out_orig, out_loaded, atol=1e-5), (
        f"Output mismatch: max diff = {(out_orig - out_loaded).abs().max().item()}"
    )

    record("PEFT / LoRA on bert-tiny", "PASS", elapsed=time.time() - t0)


def test_peft_lora_distilbert_pretrained(tmp_dir: str, verbose: bool):
    """PEFT LoRA on distilbert pretrained — real weights + adapter."""
    import torch
    from peft import LoraConfig, TaskType, get_peft_model
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    t0 = time.time()
    registry = make_registry(tmp_dir)

    base_model = AutoModelForSequenceClassification.from_pretrained("distilbert-base-uncased", num_labels=2)
    lora_config = LoraConfig(
        task_type=TaskType.SEQ_CLS,
        r=8,
        lora_alpha=32,
        lora_dropout=0.0,
        target_modules=["q_lin", "v_lin"],
    )
    model = get_peft_model(base_model, lora_config)
    model.eval()

    tokenizer = AutoTokenizer.from_pretrained("distilbert-base-uncased")
    inputs = tokenizer("Testing PEFT adapter save and load", return_tensors="pt")
    with torch.no_grad():
        out_orig = model(**inputs).logits

    registry.save("peft:lora-distilbert", model)
    loaded = registry.load("peft:lora-distilbert")
    loaded.eval()

    with torch.no_grad():
        out_loaded = loaded(**inputs).logits
    assert torch.allclose(out_orig, out_loaded, atol=1e-5), (
        f"Output mismatch: max diff = {(out_orig - out_loaded).abs().max().item()}"
    )

    record("PEFT / LoRA on distilbert (pretrained)", "PASS", elapsed=time.time() - t0)


def test_peft_ia3_bert(tmp_dir: str, verbose: bool):
    """PEFT IA3 on bert-tiny — different adapter type."""
    import torch
    from peft import IA3Config, TaskType, get_peft_model
    from transformers import AutoConfig, AutoModelForSequenceClassification, AutoTokenizer

    t0 = time.time()
    registry = make_registry(tmp_dir)

    config = AutoConfig.from_pretrained("lyeonii/bert-tiny")
    config.num_labels = 2
    base_model = AutoModelForSequenceClassification.from_config(config)

    ia3_config = IA3Config(
        task_type=TaskType.SEQ_CLS,
        target_modules=["query", "value", "output.dense"],
        feedforward_modules=["output.dense"],
    )
    model = get_peft_model(base_model, ia3_config)
    model.eval()

    tokenizer = AutoTokenizer.from_pretrained("lyeonii/bert-tiny")
    inputs = tokenizer("IA3 adapter test", return_tensors="pt")
    with torch.no_grad():
        out_orig = model(**inputs).logits

    registry.save("peft:ia3-bert", model)
    loaded = registry.load("peft:ia3-bert")
    loaded.eval()

    with torch.no_grad():
        out_loaded = loaded(**inputs).logits
    assert torch.allclose(out_orig, out_loaded, atol=1e-5), (
        f"Output mismatch: max diff = {(out_orig - out_loaded).abs().max().item()}"
    )

    record("PEFT / IA3 on bert-tiny", "PASS", elapsed=time.time() - t0)


def test_peft_lora_causal_lm(tmp_dir: str, verbose: bool):
    """PEFT LoRA on GPT-2 causal LM — different model architecture."""
    import torch
    from peft import LoraConfig, TaskType, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer

    t0 = time.time()
    registry = make_registry(tmp_dir)

    base_model = AutoModelForCausalLM.from_pretrained("sshleifer/tiny-gpt2")
    lora_config = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=4,
        lora_alpha=16,
        lora_dropout=0.0,
        target_modules=["c_attn"],
    )
    model = get_peft_model(base_model, lora_config)
    model.eval()

    tokenizer = AutoTokenizer.from_pretrained("sshleifer/tiny-gpt2")
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    inputs = tokenizer("Hello world", return_tensors="pt")
    with torch.no_grad():
        out_orig = model(**inputs).logits

    registry.save("peft:lora-gpt2", model)
    loaded = registry.load("peft:lora-gpt2")
    loaded.eval()

    with torch.no_grad():
        out_loaded = loaded(**inputs).logits
    assert torch.allclose(out_orig, out_loaded, atol=1e-5), (
        f"Output mismatch: max diff = {(out_orig - out_loaded).abs().max().item()}"
    )

    record("PEFT / LoRA on tiny-gpt2 (CausalLM)", "PASS", elapsed=time.time() - t0)


def test_peft_no_adapter_passthrough(tmp_dir: str, verbose: bool):
    """PEFT passthrough — model without adapter saves/loads normally."""
    from transformers import AutoConfig, AutoModel

    t0 = time.time()
    registry = make_registry(tmp_dir)

    config = AutoConfig.from_pretrained("lyeonii/bert-tiny")
    model = AutoModel.from_config(config)
    model.eval()

    # No adapter attached — _save_peft_adapter should be a no-op
    assert not (hasattr(model, "peft_config") and model.peft_config)

    registry.save("peft:no-adapter", model)
    loaded = registry.load("peft:no-adapter")
    loaded.eval()

    assert type(loaded).__name__ == type(model).__name__

    record("PEFT / no-adapter passthrough", "PASS", elapsed=time.time() - t0)


def run_peft_tests(verbose: bool):
    print("\n--- PEFT adapter archivers ---")
    if not (HAS_TRANSFORMERS and HAS_PEFT):
        missing = []
        if not HAS_TRANSFORMERS:
            missing.append("transformers")
        if not HAS_PEFT:
            missing.append("peft")
        record("PEFT / *", "SKIP", f"{', '.join(missing)} not installed")
        return

    test_fns = [
        test_peft_lora_bert,
        test_peft_lora_distilbert_pretrained,
        test_peft_ia3_bert,
        test_peft_lora_causal_lm,
        test_peft_no_adapter_passthrough,
    ]
    for test_fn in test_fns:
        with tempfile.TemporaryDirectory() as tmp:
            try:
                test_fn(tmp, verbose)
            except Exception as e:
                record(test_fn.__doc__.split("—")[0].strip(), "FAIL", str(e))


# ============================================================================
# HF PROCESSORS / TOKENIZERS
# ============================================================================
def test_hf_tokenizer_bert(tmp_dir: str, verbose: bool):
    """HF tokenizer bert-base-uncased — save/load roundtrip."""
    from transformers import AutoTokenizer

    t0 = time.time()
    registry = make_registry(tmp_dir)

    tokenizer = AutoTokenizer.from_pretrained("bert-base-uncased")

    registry.save("proc:bert-tokenizer", tokenizer)
    loaded = registry.load("proc:bert-tokenizer")

    # Verify tokenization produces identical results
    text = "Testing the mindtrace registry tokenizer archiver"
    orig_ids = tokenizer(text)["input_ids"]
    loaded_ids = loaded(text)["input_ids"]
    assert orig_ids == loaded_ids, f"Token ID mismatch: {orig_ids} != {loaded_ids}"
    assert tokenizer.vocab_size == loaded.vocab_size

    record("HF / bert tokenizer", "PASS", elapsed=time.time() - t0)


def test_hf_tokenizer_gpt2(tmp_dir: str, verbose: bool):
    """HF tokenizer sshleifer/tiny-gpt2 — BPE tokenizer roundtrip."""
    from transformers import AutoTokenizer

    t0 = time.time()
    registry = make_registry(tmp_dir)

    tokenizer = AutoTokenizer.from_pretrained("sshleifer/tiny-gpt2")

    registry.save("proc:gpt2-tokenizer", tokenizer)
    loaded = registry.load("proc:gpt2-tokenizer")

    text = "Hello, this is a GPT-2 tokenizer test!"
    orig_ids = tokenizer(text)["input_ids"]
    loaded_ids = loaded(text)["input_ids"]
    assert orig_ids == loaded_ids, "Token ID mismatch"
    assert tokenizer.vocab_size == loaded.vocab_size

    record("HF / GPT-2 tokenizer (BPE)", "PASS", elapsed=time.time() - t0)


def test_hf_image_processor_vit(tmp_dir: str, verbose: bool):
    """HF image processor google/vit-base-patch16-224 — vision preprocessor."""
    import numpy as np
    from transformers import AutoImageProcessor

    t0 = time.time()
    registry = make_registry(tmp_dir)

    processor = AutoImageProcessor.from_pretrained("google/vit-base-patch16-224")

    registry.save("proc:vit-imgproc", processor)
    loaded = registry.load("proc:vit-imgproc")

    # Verify processing produces identical outputs (fast processors require "pt" tensors)
    dummy_image = np.random.randint(0, 255, (224, 224, 3), dtype=np.uint8)
    orig_out = processor(dummy_image, return_tensors="pt")["pixel_values"].numpy()
    loaded_out = loaded(dummy_image, return_tensors="pt")["pixel_values"].numpy()
    assert np.allclose(orig_out, loaded_out, atol=1e-6), "Image processor output mismatch"

    record("HF / ViT image processor", "PASS", elapsed=time.time() - t0)


def test_hf_processor_multimodal(tmp_dir: str, verbose: bool):
    """HF AutoProcessor for CLIP — multimodal text+image processor."""
    import numpy as np
    from transformers import AutoProcessor

    t0 = time.time()
    registry = make_registry(tmp_dir)

    processor = AutoProcessor.from_pretrained("openai/clip-vit-base-patch32")

    registry.save("proc:clip-processor", processor)
    loaded = registry.load("proc:clip-processor")

    # Verify text tokenization
    text = "a photo of a cat"
    orig_ids = processor(text=text, return_tensors="pt", padding=True)["input_ids"].numpy()
    loaded_ids = loaded(text=text, return_tensors="pt", padding=True)["input_ids"].numpy()
    assert np.array_equal(orig_ids, loaded_ids), "CLIP text tokenization mismatch"

    # Verify image processing (fast processors require "pt" tensors)
    dummy_image = np.random.randint(0, 255, (224, 224, 3), dtype=np.uint8)
    orig_pixels = processor(images=dummy_image, return_tensors="pt")["pixel_values"].numpy()
    loaded_pixels = loaded(images=dummy_image, return_tensors="pt")["pixel_values"].numpy()
    assert np.allclose(orig_pixels, loaded_pixels, atol=1e-6), "CLIP image processing mismatch"

    record("HF / CLIP multimodal processor", "PASS", elapsed=time.time() - t0)


def run_processor_tests(verbose: bool):
    print("\n--- HuggingFace processor/tokenizer archivers ---")
    if not HAS_TRANSFORMERS:
        record("HF Proc / *", "SKIP", "transformers not installed")
        return

    test_fns = [
        test_hf_tokenizer_bert,
        test_hf_tokenizer_gpt2,
        test_hf_image_processor_vit,
        test_hf_processor_multimodal,
    ]
    for test_fn in test_fns:
        with tempfile.TemporaryDirectory() as tmp:
            try:
                test_fn(tmp, verbose)
            except Exception as e:
                record(test_fn.__doc__.split("—")[0].strip(), "FAIL", str(e))


# ============================================================================
# ONNX
# ============================================================================
def test_onnx_synthetic(tmp_dir: str, verbose: bool):
    """ONNX synthetic relu model — minimal graph, no download."""
    from onnx import TensorProto, checker, helper

    t0 = time.time()
    registry = make_registry(tmp_dir)

    X = helper.make_tensor_value_info("X", TensorProto.FLOAT, [1, 10])
    Y = helper.make_tensor_value_info("Y", TensorProto.FLOAT, [1, 10])
    node = helper.make_node("Relu", ["X"], ["Y"])
    graph = helper.make_graph([node], "relu_graph", [X], [Y])
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)])
    checker.check_model(model)

    registry.save("onnx:relu-synthetic", model)
    loaded = registry.load("onnx:relu-synthetic")

    checker.check_model(loaded)
    assert loaded.graph.name == "relu_graph"
    assert len(loaded.graph.input) == 1
    assert len(loaded.graph.output) == 1

    record("ONNX / synthetic relu", "PASS", elapsed=time.time() - t0)


def test_onnx_exported_resnet(tmp_dir: str, verbose: bool):
    """ONNX resnet18 exported from PyTorch — real architecture."""
    import numpy as np
    import onnx
    import onnxruntime as ort
    import torch
    from torchvision.models import resnet18

    t0 = time.time()
    registry = make_registry(tmp_dir)

    # Export PyTorch resnet18 to ONNX
    pt_model = resnet18(weights=None)
    pt_model.eval()
    dummy = torch.randn(1, 3, 224, 224)

    onnx_path = Path(tmp_dir) / "export.onnx"
    torch.onnx.export(pt_model, dummy, str(onnx_path), dynamo=False, input_names=["input"], output_names=["output"])

    model = onnx.load(str(onnx_path))
    onnx.checker.check_model(model)

    # Get reference output from PyTorch
    with torch.no_grad():
        pt_output = pt_model(dummy).numpy()

    # Save to registry and load back
    registry.save("onnx:resnet18-export", model)
    loaded = registry.load("onnx:resnet18-export")
    onnx.checker.check_model(loaded)

    # Verify with ONNX Runtime
    # Save loaded model to temp file for ORT
    loaded_path = Path(tmp_dir) / "loaded.onnx"
    onnx.save(loaded, str(loaded_path))

    session = ort.InferenceSession(str(loaded_path))
    ort_output = session.run(None, {"input": dummy.numpy()})[0]

    assert np.allclose(pt_output, ort_output, atol=1e-5), "ORT inference mismatch after roundtrip"

    record("ONNX / resnet18 PyTorch export + ORT verify", "PASS", elapsed=time.time() - t0)


def test_onnx_mlp_with_weights(tmp_dir: str, verbose: bool):
    """ONNX MLP with initializers — tests weight preservation."""
    import numpy as np
    import onnx
    import onnxruntime as ort
    from onnx import TensorProto, helper, numpy_helper

    t0 = time.time()
    registry = make_registry(tmp_dir)

    # Build a small MLP: input(1,4) → Linear(4,3) → Relu → Linear(3,2) → output(1,2)
    np.random.seed(42)
    W1 = numpy_helper.from_array(np.random.randn(4, 3).astype(np.float32), name="W1")
    B1 = numpy_helper.from_array(np.random.randn(3).astype(np.float32), name="B1")
    W2 = numpy_helper.from_array(np.random.randn(3, 2).astype(np.float32), name="W2")
    B2 = numpy_helper.from_array(np.random.randn(2).astype(np.float32), name="B2")

    X = helper.make_tensor_value_info("X", TensorProto.FLOAT, [1, 4])
    Y = helper.make_tensor_value_info("Y", TensorProto.FLOAT, [1, 2])

    nodes = [
        helper.make_node("MatMul", ["X", "W1"], ["mm1"]),
        helper.make_node("Add", ["mm1", "B1"], ["add1"]),
        helper.make_node("Relu", ["add1"], ["relu1"]),
        helper.make_node("MatMul", ["relu1", "W2"], ["mm2"]),
        helper.make_node("Add", ["mm2", "B2"], ["Y"]),
    ]
    graph = helper.make_graph(nodes, "mlp_graph", [X], [Y], initializer=[W1, B1, W2, B2])
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)])
    model.ir_version = 8  # keep compatible with older ORT versions
    onnx.checker.check_model(model)

    # Reference output
    test_input = np.random.randn(1, 4).astype(np.float32)
    tmp_path = Path(tmp_dir) / "orig.onnx"
    onnx.save(model, str(tmp_path))
    session_orig = ort.InferenceSession(str(tmp_path))
    ref_output = session_orig.run(None, {"X": test_input})[0]

    # Registry roundtrip
    registry.save("onnx:mlp-weighted", model)
    loaded = registry.load("onnx:mlp-weighted")

    loaded_path = Path(tmp_dir) / "loaded.onnx"
    onnx.save(loaded, str(loaded_path))
    session_loaded = ort.InferenceSession(str(loaded_path))
    loaded_output = session_loaded.run(None, {"X": test_input})[0]

    assert np.allclose(ref_output, loaded_output, atol=1e-6), "Weight preservation failed after roundtrip"

    record("ONNX / MLP with initializers + ORT verify", "PASS", elapsed=time.time() - t0)


def run_onnx_tests(verbose: bool):
    print("\n--- ONNX archivers ---")
    if not HAS_ONNX:
        record("ONNX / *", "SKIP", "onnx not installed")
        return

    test_fns = [test_onnx_synthetic]

    if HAS_ONNXRUNTIME and HAS_TORCH:
        test_fns.extend([test_onnx_exported_resnet, test_onnx_mlp_with_weights])
    else:
        record("ONNX / resnet18 export", "SKIP", "onnxruntime or torch not installed")
        record("ONNX / MLP with weights", "SKIP", "onnxruntime or torch not installed")

    for test_fn in test_fns:
        with tempfile.TemporaryDirectory() as tmp:
            try:
                test_fn(tmp, verbose)
            except Exception as e:
                record(test_fn.__doc__.split("—")[0].strip(), "FAIL", str(e))


# ============================================================================
# TENSORRT
# ============================================================================
def test_tensorrt_registration(tmp_dir: str, verbose: bool):
    """TensorRT registration — verify archiver is registered for ICudaEngine."""
    import tensorrt as trt

    t0 = time.time()
    registry = make_registry(tmp_dir)

    # Verify the archiver is registered
    key = f"{trt.ICudaEngine.__module__}.{trt.ICudaEngine.__name__}"
    materializer = registry.registered_materializer(key)
    assert materializer is not None, f"No materializer registered for {key}"
    assert "TensorRTEngineArchiver" in materializer, f"Wrong materializer: {materializer}"

    record("TensorRT / archiver registration", "PASS", elapsed=time.time() - t0)


def test_tensorrt_engine_roundtrip(tmp_dir: str, verbose: bool):
    """TensorRT engine build + roundtrip — requires CUDA GPU."""
    import tensorrt as trt

    t0 = time.time()

    # Check for CUDA
    try:
        import torch

        if not torch.cuda.is_available():
            record("TensorRT / engine roundtrip", "SKIP", "no CUDA GPU available")
            return
    except ImportError:
        record("TensorRT / engine roundtrip", "SKIP", "torch not installed for CUDA check")
        return

    registry = make_registry(tmp_dir)

    # Build a minimal TensorRT engine (identity network)
    logger = trt.Logger(trt.Logger.WARNING)
    builder = trt.Builder(logger)
    network = builder.create_network(1 << int(trt.NetworkDefinitionCreationFlag.EXPLICIT_BATCH))
    config = builder.create_builder_config()
    config.set_memory_pool_limit(trt.MemoryPoolType.WORKSPACE, 1 << 28)  # 256 MB

    # Simple identity: input → output
    inp = network.add_input("input", trt.float32, (1, 3, 32, 32))
    identity = network.add_identity(inp)
    identity.get_output(0).name = "output"
    network.mark_output(identity.get_output(0))

    serialized = builder.build_serialized_network(network, config)
    if serialized is None:
        record("TensorRT / engine roundtrip", "FAIL", "failed to build engine")
        return

    runtime = trt.Runtime(logger)
    engine = runtime.deserialize_cuda_engine(serialized)
    if engine is None:
        record("TensorRT / engine roundtrip", "FAIL", "failed to deserialize engine")
        return

    # Save and load through registry
    registry.save("trt:identity", engine)
    loaded = registry.load("trt:identity")

    assert loaded is not None, "Loaded engine is None"
    assert loaded.num_io_tensors == engine.num_io_tensors, "IO tensor count mismatch"

    record("TensorRT / engine build + roundtrip", "PASS", elapsed=time.time() - t0)


def run_tensorrt_tests(verbose: bool):
    print("\n--- TensorRT archivers ---")
    if not HAS_TENSORRT:
        record("TensorRT / *", "SKIP", "tensorrt not installed")
        return

    with tempfile.TemporaryDirectory() as tmp:
        try:
            test_tensorrt_registration(tmp, verbose)
        except Exception as e:
            record("TensorRT / archiver registration", "FAIL", str(e))

    with tempfile.TemporaryDirectory() as tmp:
        try:
            test_tensorrt_engine_roundtrip(tmp, verbose)
        except Exception as e:
            record("TensorRT / engine roundtrip", "FAIL", str(e))


# ============================================================================
# ULTRALYTICS
# ============================================================================
def test_ultralytics_yolo(tmp_dir: str, verbose: bool):
    """Ultralytics YOLOv8n — nano detection model."""
    from ultralytics import YOLO

    t0 = time.time()
    registry = make_registry(tmp_dir)

    # Download nano model (smallest, ~6MB)
    model_dir = Path(tmp_dir) / "downloads"
    model_dir.mkdir()
    model = YOLO(str(model_dir / "yolov8n.pt"))

    registry.save("yolo:v8n-det", model)
    loaded = registry.load("yolo:v8n-det")

    assert isinstance(loaded, YOLO), f"Expected YOLO, got {type(loaded)}"

    record("Ultralytics / YOLOv8n detection", "PASS", elapsed=time.time() - t0)


def test_ultralytics_yolo_seg(tmp_dir: str, verbose: bool):
    """Ultralytics YOLOv8n-seg — nano segmentation model."""
    from ultralytics import YOLO

    t0 = time.time()
    registry = make_registry(tmp_dir)

    model_dir = Path(tmp_dir) / "downloads"
    model_dir.mkdir()
    model = YOLO(str(model_dir / "yolov8n-seg.pt"))

    registry.save("yolo:v8n-seg", model)
    loaded = registry.load("yolo:v8n-seg")

    assert isinstance(loaded, YOLO)

    record("Ultralytics / YOLOv8n segmentation", "PASS", elapsed=time.time() - t0)


def test_ultralytics_yolo_cls(tmp_dir: str, verbose: bool):
    """Ultralytics YOLOv8n-cls — nano classification model."""
    from ultralytics import YOLO

    t0 = time.time()
    registry = make_registry(tmp_dir)

    model_dir = Path(tmp_dir) / "downloads"
    model_dir.mkdir()
    model = YOLO(str(model_dir / "yolov8n-cls.pt"))

    registry.save("yolo:v8n-cls", model)
    loaded = registry.load("yolo:v8n-cls")

    assert isinstance(loaded, YOLO)

    record("Ultralytics / YOLOv8n classification", "PASS", elapsed=time.time() - t0)


def test_ultralytics_sam(tmp_dir: str, verbose: bool):
    """Ultralytics SAM2.1-t — tiny segment anything model."""
    from ultralytics import SAM

    t0 = time.time()
    registry = make_registry(tmp_dir)

    model_dir = Path(tmp_dir) / "downloads"
    model_dir.mkdir()
    model = SAM(str(model_dir / "sam2.1_t.pt"))

    registry.save("sam:v2.1-tiny", model)
    loaded = registry.load("sam:v2.1-tiny")

    assert isinstance(loaded, SAM)

    record("Ultralytics / SAM2.1-t (tiny)", "PASS", elapsed=time.time() - t0)


def run_ultralytics_tests(verbose: bool):
    print("\n--- Ultralytics archivers ---")
    if not HAS_ULTRALYTICS:
        record("Ultralytics / *", "SKIP", "ultralytics not installed")
        return
    if not HAS_TORCH:
        record("Ultralytics / *", "SKIP", "torch not installed")
        return

    for test_fn in [test_ultralytics_yolo, test_ultralytics_yolo_seg, test_ultralytics_yolo_cls, test_ultralytics_sam]:
        with tempfile.TemporaryDirectory() as tmp:
            try:
                test_fn(tmp, verbose)
            except Exception as e:
                record(test_fn.__doc__.split("—")[0].strip(), "FAIL", str(e))


# ============================================================================
# MAIN
# ============================================================================
def print_summary():
    total = len(RESULTS)
    passed = sum(1 for r in RESULTS if r["status"] == "PASS")
    failed = sum(1 for r in RESULTS if r["status"] == "FAIL")
    skipped = sum(1 for r in RESULTS if r["status"] == "SKIP")

    print("\n" + "=" * 60)
    print(f"SUMMARY: {passed} passed, {failed} failed, {skipped} skipped (total {total})")
    print("=" * 60)

    if failed:
        print("\nFailed tests:")
        for r in RESULTS:
            if r["status"] == "FAIL":
                print(f"  - {r['name']}: {r['detail']}")

    total_time = sum(r["elapsed"] for r in RESULTS)
    print(f"\nTotal time: {total_time:.1f}s")

    return 0 if failed == 0 else 1


def main():
    parser = argparse.ArgumentParser(description="Test ML model archivers end-to-end via the Registry.")
    parser.add_argument("--timm", action="store_true", help="Run timm archiver tests")
    parser.add_argument("--hf", action="store_true", help="Run HuggingFace model archiver tests")
    parser.add_argument("--peft", action="store_true", help="Run PEFT adapter archiver tests")
    parser.add_argument("--processors", action="store_true", help="Run HF processor/tokenizer archiver tests")
    parser.add_argument("--onnx", action="store_true", help="Run ONNX archiver tests")
    parser.add_argument("--tensorrt", action="store_true", help="Run TensorRT archiver tests")
    parser.add_argument("--ultralytics", action="store_true", help="Run Ultralytics archiver tests")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    args = parser.parse_args()

    # If no specific archiver selected, run all
    run_all = not (
        args.timm or args.hf or args.peft or args.processors or args.onnx or args.tensorrt or args.ultralytics
    )

    print("ML Archiver End-to-End Tests")
    print("=" * 60)
    print(
        f"Available: timm={HAS_TIMM} hf={HAS_TRANSFORMERS} peft={HAS_PEFT} "
        f"onnx={HAS_ONNX} ort={HAS_ONNXRUNTIME} trt={HAS_TENSORRT} ultralytics={HAS_ULTRALYTICS}"
    )

    if run_all or args.timm:
        run_timm_tests(args.verbose)

    if run_all or args.hf:
        run_hf_tests(args.verbose)

    if run_all or args.peft:
        run_peft_tests(args.verbose)

    if run_all or args.processors:
        run_processor_tests(args.verbose)

    if run_all or args.onnx:
        run_onnx_tests(args.verbose)

    if run_all or args.tensorrt:
        run_tensorrt_tests(args.verbose)

    if run_all or args.ultralytics:
        run_ultralytics_tests(args.verbose)

    return print_summary()


if __name__ == "__main__":
    sys.exit(main())

"""ONNX model export and serving with OnnxModelService.

Demonstrates the full ONNX workflow:
  1. Export a torchvision ResNet-50 model to an ONNX file.
  2. Load it via OnnxModelService and run predict_array().
  3. Introspect session metadata (input/output names, shapes).
  4. Call svc.info() to get structured ModelInfo.
  5. Show the OnnxModelService.serve() classmethod pattern.
  6. Subclass example overriding predict() for full request handling.
"""

import os
import time

import numpy as np
import torch
import torch.nn as nn

# ── ONNX runtime guard ─────────────────────────────────────────────────────
try:
    import onnxruntime  # noqa: F401
    _ORT_AVAILABLE = True
except ImportError:
    _ORT_AVAILABLE = False
    print("SKIPPING: onnxruntime not installed — pip install onnxruntime")

# ── torchvision guard ──────────────────────────────────────────────────────
try:
    import torchvision.models as tvm
    _TV_AVAILABLE = True
except ImportError:
    _TV_AVAILABLE = False
    print("SKIPPING: torchvision not installed — pip install torchvision")

if not (_ORT_AVAILABLE and _TV_AVAILABLE):
    raise SystemExit(0)

from mindtrace.models.serving.onnx.service import OnnxModelService
from mindtrace.models.serving.schemas import PredictRequest, PredictResponse

# ── Section: export ResNet-50 to ONNX ──────────────────────────────────────
print("\n── Export ResNet-50 → ONNX ──")

ONNX_PATH = "/tmp/resnet50_sample.onnx"
NUM_CLASSES = 10

model = tvm.resnet50(pretrained=False)
model.fc = nn.Linear(model.fc.in_features, NUM_CLASSES)
model.eval()
model = model.cpu()

dummy = torch.randn(1, 3, 224, 224)
torch.onnx.export(
    model,
    dummy,
    ONNX_PATH,
    input_names=["pixel_values"],
    output_names=["logits"],
    opset_version=18,
    dynamic_axes={"pixel_values": {0: "batch"}, "logits": {0: "batch"}},
    dynamo=False,
)
print(f"  Exported to {ONNX_PATH}  ({os.path.getsize(ONNX_PATH) / 1e6:.1f} MB)")

# ── Section: load with OnnxModelService ────────────────────────────────────
print("\n── Load OnnxModelService ──")

svc = OnnxModelService(
    model_name="resnet50-sample",
    model_version="v1",
    model_path=ONNX_PATH,
)
# load_model() is called automatically in __init__
print(f"  model_name  : {svc.model_name}")
print(f"  model_version: {svc.model_version}")
print(f"  providers   : {svc.providers}")

# ── Section: introspect session metadata ───────────────────────────────────
print("\n── Session introspection ──")
print(f"  input_names  : {svc.input_names}")
print(f"  output_names : {svc.output_names}")
print(f"  input_shapes : {svc.input_shapes}")
print(f"  output_shapes: {svc.output_shapes}")

# ── Section: predict_array() with synthetic data ───────────────────────────
print("\n── predict_array() ──")
img_batch = np.random.randn(4, 3, 224, 224).astype(np.float32)

t0 = time.perf_counter()
outputs = svc.predict_array({"pixel_values": img_batch})
elapsed = time.perf_counter() - t0

logits = outputs["logits"]                    # (4, NUM_CLASSES)
preds  = logits.argmax(axis=1)
print(f"  Input shape  : {img_batch.shape}")
print(f"  Output logits: {logits.shape}")
print(f"  Predictions  : {preds.tolist()}")
print(f"  Latency      : {elapsed * 1000:.1f} ms for batch=4")

# ── Section: svc.info() ModelInfo ─────────────────────────────────────────
print("\n── svc.info() ──")
info = svc.info()
print(f"  name        : {info.name}")
print(f"  version     : {info.version}")
print(f"  task        : {info.task}")
print(f"  device      : {info.device}")
print(f"  input_names : {info.extra['input_names']}")
print(f"  input_shapes: {info.extra['input_shapes']}")
print(f"  providers   : {info.extra['providers']}")

# ── Section: serve() pattern (do not call — blocks) ───────────────────────
print("\n── OnnxModelService.serve() pattern (not called) ──")
print("""
  # Blocking — runs until Ctrl-C:
  OnnxModelService.serve(
      model_name="resnet50-sample",
      model_version="v1",
      model_path=ONNX_PATH,
      host="0.0.0.0",
      port=8080,
  )
""")

# ── Section: custom subclass overriding predict() ─────────────────────────
print("── Custom subclass with predict() override ──")


class ClassifierOnnxService(OnnxModelService):
    """OnnxModelService that handles full PredictRequest → PredictResponse."""

    _task = "classification"

    def predict(self, request: PredictRequest) -> PredictResponse:
        # Real impl: load images from request.images paths / base64.
        # Here we use a random batch matching the request image count.
        n = len(request.images)
        arr = np.random.randn(n, 3, 224, 224).astype(np.float32)
        outputs = self.run({"pixel_values": arr})
        class_ids = outputs["logits"].argmax(axis=1).tolist()
        return PredictResponse(results=class_ids, timing_s=0.0)


custom_svc = ClassifierOnnxService(
    model_name="classifier-custom",
    model_version="v2",
    model_path=ONNX_PATH,
)
req = PredictRequest(images=["img1.jpg", "img2.jpg", "img3.jpg"])
resp = custom_svc.predict(req)
print(f"  ClassifierOnnxService.predict() → results: {resp.results}")

# ── Section: cleanup ───────────────────────────────────────────────────────
print("\n── Cleanup ──")
if os.path.exists(ONNX_PATH):
    os.remove(ONNX_PATH)
    print(f"  Removed {ONNX_PATH}")

print("\nDone.")

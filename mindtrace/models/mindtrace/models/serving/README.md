# mindtrace.models.serving

Model inference services with a uniform `predict()` interface.
Two runtime backends are provided: ONNX (CPU/GPU via onnxruntime)
and TorchServe.

```python
# Base abstractions
from mindtrace.models.serving import ModelService, PredictRequest, PredictResponse, ModelInfo

# ONNX (most common — zero-subclass path)
from mindtrace.models.serving.onnx import OnnxModelService

# TorchServe proxy
from mindtrace.models.serving.torchserve import TorchServeModelService, TorchServeExporter
```

---

## ModelService -- abstract base

Subclass this when writing a custom inference backend.

```python
from mindtrace.models.serving import ModelService, PredictRequest, PredictResponse

class MyService(ModelService):
    _task = "classification"           # informational string

    def load_model(self) -> None:
        # Called automatically in __init__
        self.model = torch.load(f"{self.model_name}.pt")
        self.model.to(self.device).eval()

    def predict(self, request: PredictRequest) -> PredictResponse:
        imgs   = [preprocess(p) for p in request.images]
        tensor = torch.stack(imgs).to(self.device)
        with torch.no_grad():
            logits = self.model(tensor)
        return PredictResponse(results=logits.argmax(1).tolist(), timing_s=0.0)

svc = MyService(
    model_name="my-classifier",
    model_version="v1",
    device="auto",        # "auto" | "cuda" | "cuda:1" | "cpu"
    registry=None,        # optional Registry -- used in load_model if needed
)

# Start as HTTP server (any subclass)
MyService.serve(host="0.0.0.0", port=8080)
```

---

## ONNX -- `OnnxModelService`

### Zero-subclass path (recommended)

```python
from mindtrace.models.serving.onnx import OnnxModelService
import numpy as np

svc = OnnxModelService(
    model_name="weld-classifier",
    model_version="v3",
    model_path="model.onnx",          # local .onnx file
    providers=None,                    # None = auto (CUDAExecutionProvider if available)
    session_options=None,              # onnxruntime.SessionOptions
)

# Run inference from preprocessed numpy arrays
outputs = svc.predict_array({
    "pixel_values": np.random.randn(4, 3, 224, 224).astype(np.float32)
})
# -> {"logits": ndarray (4, num_classes)}
```

### Load from registry instead of file

```python
svc = OnnxModelService(
    model_name="weld-classifier",
    model_version="v3",
    registry=my_registry,    # calls registry.load("weld-classifier:v3")
)
```

### Session introspection

```python
svc.input_names     # ["pixel_values"]
svc.output_names    # ["logits"]
svc.input_shapes    # {"pixel_values": [None, 3, 224, 224]}
svc.output_shapes   # {"logits": [None, 10]}
svc.info()          # ModelInfo(name=..., version=..., device=..., ...)
```

### Custom subclass path

Use when you need full image loading / pre- and post-processing:

```python
class WeldService(OnnxModelService):
    _task = "classification"

    def predict(self, request: PredictRequest) -> PredictResponse:
        imgs = np.stack([load_and_normalize(p) for p in request.images])
        out  = self.run({"pixel_values": imgs.astype(np.float32)})
        return PredictResponse(
            results=out["logits"].argmax(axis=1).tolist(),
            timing_s=0.0,
        )
```

### ONNX export

```python
import torch

model.eval()
torch.onnx.export(
    model.cpu(),
    torch.randn(1, 3, 224, 224),
    "model.onnx",
    input_names=["pixel_values"],
    output_names=["logits"],
    dynamic_axes={"pixel_values": {0: "batch"}, "logits": {0: "batch"}},
    opset_version=17,
)
```

---

## TorchServe -- `TorchServeModelService`

HTTP proxy to a running TorchServe inference server.

```python
from mindtrace.models.serving.torchserve import TorchServeModelService, TorchServeExporter

# Proxy client
svc = TorchServeModelService(
    model_name="weld-classifier",
    model_version="v3",
    ts_inference_url="http://localhost:8080",
    ts_management_url="http://localhost:8081",
    ts_model_name="weld_v3",           # model name registered in TorchServe
    timeout_s=30.0,
)
resp = svc.predict(PredictRequest(images=["img.jpg"]))

# Export to TorchServe .mar archive
exporter = TorchServeExporter(model=model, model_name="weld-classifier")
exporter.export(output_dir="/tmp/ts_models")
```

---

## Request / Response schemas

```python
from mindtrace.models.serving import PredictRequest, PredictResponse, ModelInfo

req  = PredictRequest(
    images=["path/to/img.jpg", "path/to/img2.jpg"],
    params={"threshold": 0.5},   # optional model-specific overrides
)

resp = PredictResponse(
    results=[{"class": "weld_ok", "score": 0.97}],
    timing_s=0.012,
)

info = ModelInfo(
    name="my-model",
    version="v1",
    device="cuda",
    task="classification",
    extra={"onnx_opset": 17},
)
```

---

## Backend comparison

| Feature | ONNX | TorchServe |
|---------|------|------------|
| Hardware | CPU / GPU | CPU / GPU |
| Zero-subclass inference | Yes | No |
| Dynamic batch size | Yes | Yes |
| HTTP serving | via `serve()` | native |
| FP16 | provider-dependent | Yes |
| Python dependency | `onnxruntime` | TorchServe server |

[![PyPI version](https://img.shields.io/pypi/v/mindtrace-models)](https://pypi.org/project/mindtrace-models/)

# Mindtrace Models -- Serving

Model inference services with a uniform `predict()` interface. Two runtime backends are provided: ONNX Runtime (CPU/GPU via onnxruntime) and TorchServe.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [ModelService Base](#modelservice-base)
- [ONNX Backend](#onnx-backend)
- [TorchServe Backend](#torchserve-backend)
- [Request and Response Schemas](#request-and-response-schemas)
- [Backend Comparison](#backend-comparison)
- [Configuration](#configuration)
- [API Reference](#api-reference)

## Overview

The serving sub-package provides:

- **ModelService**: Abstract base class extending `mindtrace.services.Service` (FastAPI + Uvicorn) with `/predict` and `/info` endpoints
- **OnnxModelService**: Zero-subclass inference via ONNX Runtime with automatic provider selection
- **TorchServeModelService**: HTTP proxy to a running TorchServe inference server
- **TorchServeExporter**: Export models to TorchServe `.mar` archive format
- **Typed Schemas**: `PredictRequest`, `PredictResponse`, `ModelInfo` for structured I/O

## Architecture

```
serving/
├── __init__.py              # ModelService, schemas, resolve_device
├── base.py                  # ModelService abstract base class
├── schemas.py               # PredictRequest, PredictResponse, ModelInfo, result types
├── onnx/
│   ├── __init__.py
│   └── service.py           # OnnxModelService
└── torchserve/
    ├── __init__.py
    ├── service.py           # TorchServeModelService
    ├── exporter.py          # TorchServeExporter
    └── handler.py           # MindtraceHandler (TorchServe custom handler)
```

## ModelService Base

All model services expose a standard interface via HTTP.

### Service Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/predict` | POST | Run inference on input data |
| `/info` | GET | Return model metadata (`ModelInfo`) |

### Subclassing

```python
from mindtrace.models.serving import ModelService, PredictRequest, PredictResponse

class MyService(ModelService):
    _task = "classification"

    def load_model(self) -> None:
        # Called automatically in __init__
        self.model = torch.load(f"{self.model_name}.pt")
        self.model.to(self.device).eval()

    def predict(self, request: PredictRequest) -> PredictResponse:
        imgs = [preprocess(p) for p in request.images]
        tensor = torch.stack(imgs).to(self.device)
        with torch.no_grad():
            logits = self.model(tensor)
        return PredictResponse(results=logits.argmax(1).tolist(), timing_s=0.0)

svc = MyService(
    model_name="my-classifier",
    model_version="v1",
    device="auto",
    registry=None,
)

# Start as HTTP server
MyService.serve(host="0.0.0.0", port=8080)
```

### Constructor Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model_name` | `str` | required | Model identifier |
| `model_version` | `str` | required | Version string |
| `device` | `str` | `"auto"` | `"auto"`, `"cuda"`, `"cuda:1"`, `"cpu"` |
| `registry` | `Registry` or `None` | `None` | Optional registry for model loading |

## ONNX Backend

### Zero-Subclass Path (Recommended)

```python
from mindtrace.models.serving.onnx import OnnxModelService
import numpy as np

svc = OnnxModelService(
    model_name="weld-classifier",
    model_version="v3",
    model_path="model.onnx",
    providers=None,              # None = auto (CUDAExecutionProvider if available)
    session_options=None,        # onnxruntime.SessionOptions
)

outputs = svc.predict_array({
    "pixel_values": np.random.randn(4, 3, 224, 224).astype(np.float32)
})
# -> {"logits": ndarray (4, num_classes)}
```

### Load from Registry

```python
svc = OnnxModelService(
    model_name="weld-classifier",
    model_version="v3",
    registry=my_registry,        # calls registry.load("weld-classifier:v3")
)
```

### Session Introspection

```python
svc.input_names     # ["pixel_values"]
svc.output_names    # ["logits"]
svc.input_shapes    # {"pixel_values": [None, 3, 224, 224]}
svc.output_shapes   # {"logits": [None, 10]}
svc.info()          # ModelInfo(name=..., version=..., device=..., ...)
```

### OnnxModelService Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model_path` | `str` or `None` | `None` | Local `.onnx` file path |
| `providers` | `list[str]` or `None` | `None` | ONNX Runtime execution providers |
| `session_options` | `SessionOptions` or `None` | `None` | Runtime session options |

### Custom Subclass Path

Use when you need full image loading / pre- and post-processing:

```python
class WeldService(OnnxModelService):
    _task = "classification"

    def predict(self, request: PredictRequest) -> PredictResponse:
        imgs = np.stack([load_and_normalize(p) for p in request.images])
        out = self.run({"pixel_values": imgs.astype(np.float32)})
        return PredictResponse(
            results=out["logits"].argmax(axis=1).tolist(),
            timing_s=0.0,
        )
```

### ONNX Export

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

## TorchServe Backend

### TorchServeModelService

HTTP proxy to a running TorchServe inference server.

```python
from mindtrace.models.serving.torchserve import TorchServeModelService

svc = TorchServeModelService(
    model_name="weld-classifier",
    model_version="v3",
    ts_inference_url="http://localhost:8080",
    ts_management_url="http://localhost:8081",
    ts_model_name="weld_v3",
    timeout_s=30.0,
)
resp = svc.predict(PredictRequest(images=["img.jpg"]))
```

### TorchServeModelService Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `ts_inference_url` | `str` | required | TorchServe inference endpoint |
| `ts_management_url` | `str` | required | TorchServe management endpoint |
| `ts_model_name` | `str` | required | Model name registered in TorchServe |
| `timeout_s` | `float` | `30.0` | HTTP request timeout |

### TorchServeExporter

Export a model to TorchServe `.mar` archive format.

```python
from mindtrace.models.serving.torchserve import TorchServeExporter

exporter = TorchServeExporter(model=model, model_name="weld-classifier")
exporter.export(output_dir="/tmp/ts_models")
```

## Request and Response Schemas

```python
from mindtrace.models.serving import PredictRequest, PredictResponse, ModelInfo

req = PredictRequest(
    images=["path/to/img.jpg", "path/to/img2.jpg"],
    params={"threshold": 0.5},
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

### Typed Result Classes

| Class | Task | Fields |
|-------|------|--------|
| `ClassificationResult` | Classification | `class_name`, `score`, `class_id` |
| `DetectionResult` | Detection | `boxes`, `scores`, `labels` |
| `SegmentationResult` | Segmentation | `mask`, `class_ids` |

## Backend Comparison

| Feature | ONNX | TorchServe |
|---------|------|------------|
| Hardware | CPU / GPU | CPU / GPU |
| Zero-subclass inference | Yes | No |
| Dynamic batch size | Yes | Yes |
| HTTP serving | via `serve()` | native |
| FP16 | provider-dependent | Yes |
| Python dependency | `onnxruntime` | TorchServe server |
| Model format | `.onnx` | `.mar` archive |
| Requires external server | No | Yes |

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `MINDTRACE_DEVICE` | Device selection | `"auto"` |
| `MINDTRACE_MODEL_SERVICE_HOST` | Service bind host | `"0.0.0.0"` |
| `MINDTRACE_MODEL_SERVICE_PORT` | Service bind port | `8080` |

## API Reference

```python
from mindtrace.models.serving import (
    # Base
    ModelService,               # abstract base (extends mindtrace.services.Service)
    ModelInfo,                  # model metadata schema
    PredictRequest,             # inference request schema
    PredictResponse,            # inference response schema
    resolve_device,             # "auto" -> "cuda" or "cpu"

    # Typed results
    ClassificationResult,       # typed classification output
    DetectionResult,            # typed detection output
    SegmentationResult,         # typed segmentation output
)

from mindtrace.models.serving.onnx import (
    OnnxModelService,           # ONNX Runtime inference service
)

from mindtrace.models.serving.torchserve import (
    TorchServeModelService,     # TorchServe proxy client
    TorchServeExporter,         # .mar archive exporter
    MindtraceHandler,           # TorchServe custom handler
)
```

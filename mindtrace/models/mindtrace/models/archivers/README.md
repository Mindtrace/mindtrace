[![PyPI version](https://img.shields.io/pypi/v/mindtrace-models)](https://pypi.org/project/mindtrace-models/)

# Mindtrace Models -- Archivers

ML model serialization and deserialization for the Mindtrace Registry. Each archiver handles a specific model framework and self-registers with the Registry at import time so that `registry.save()` and `registry.load()` automatically select the correct serialization strategy based on the model type.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Self-Registration](#self-registration)
- [Archiver Reference](#archiver-reference)
- [Usage](#usage)
- [Registration Order and Dispatch](#registration-order-and-dispatch)
- [Dependencies](#dependencies)
- [API Reference](#api-reference)

## Overview

The archivers sub-package provides:

- **Automatic Registration**: Archivers register themselves when `mindtrace.models` is imported; no manual setup needed
- **Type-Based Dispatch**: The Registry resolves the correct archiver by walking the MRO of the saved object
- **Guard Imports**: Missing optional dependencies (e.g. `transformers`, `ultralytics`) do not prevent the rest of the framework from loading
- **Seven Archivers**: HuggingFace models, HuggingFace processors, ONNX, timm, YOLO, YOLOE, SAM

## Architecture

```
archivers/
├── __init__.py              # register_ml_archivers() entry point
├── huggingface/
│   ├── hf_model_archiver.py       # HuggingFaceModelArchiver
│   └── hf_processor_archiver.py   # HuggingFaceProcessorArchiver
├── timm/
│   └── timm_model_archiver.py     # TimmModelArchiver
├── onnx/
│   └── onnx_model_archiver.py     # OnnxModelArchiver
└── ultralytics/
    ├── yolo_archiver.py            # YoloArchiver
    ├── yoloe_archiver.py           # YoloEArchiver
    └── sam_archiver.py             # SamArchiver
```

## Self-Registration

When `mindtrace.models.archivers` is imported, the package-level `register_ml_archivers()` function imports each archiver module. Each module calls `Registry.register_default_materializer(ModelType, ArchiverClass)` at module scope.

Registration is guarded by `try/except ImportError` so missing optional dependencies do not prevent the rest of the framework from loading.

```python
# Simplified registration flow (happens automatically):
from mindtrace.registry import Registry

# Inside hf_model_archiver.py:
from transformers import PreTrainedModel
Registry.register_default_materializer(PreTrainedModel, HuggingFaceModelArchiver)

# Inside yolo_archiver.py:
from ultralytics import YOLO, YOLOWorld
Registry.register_default_materializer(YOLO, YoloArchiver)
Registry.register_default_materializer(YOLOWorld, YoloArchiver)
```

## Archiver Reference

| Archiver | Model Type | Extra | Auto-registered | Serialization format |
|----------|-----------|-------|-----------------|---------------------|
| `HuggingFaceModelArchiver` | `PreTrainedModel`, `PeftModel` | `transformers` | Yes | `config.json` + `pytorch_model.bin` or `model.safetensors` |
| `HuggingFaceProcessorArchiver` | `ProcessorMixin`, `PreTrainedTokenizerBase`, `ImageProcessingMixin`, `FeatureExtractionMixin` | `transformers` | Yes | Standard HF processor layout |
| `OnnxModelArchiver` | `onnx.ModelProto` | `onnx` | Yes | `model.onnx` + `metadata.json` |
| `TimmModelArchiver` | timm models (`nn.Module` with `pretrained_cfg`) | `timm` | No (explicit) | `config.json` + `model.pt` |
| `YoloArchiver` | `ultralytics.YOLO`, `ultralytics.YOLOWorld` | `ultralytics` | Yes | `model.pt` |
| `YoloEArchiver` | `ultralytics.YOLOE` | `ultralytics` | Yes | `model.pt` |
| `SamArchiver` | `ultralytics.SAM` | `ultralytics` | Yes | `{variant}_model.pt` |

### SamArchiver Supported Variants

`sam_b`, `sam_l`, `sam2_t`, `sam2_s`, `sam2_b`, `sam2_l`, `sam2.1_t`, `sam2.1_s`, `sam2.1_b`, `sam2.1_l`

The variant is identified by parameter count and encoded in the filename so the correct model is rebuilt on load.

## Usage

### Automatic (Recommended)

```python
import mindtrace.models  # triggers archiver registration

registry.save("my-model:v1", model)   # archiver selected automatically by type
model = registry.load("my-model:v1")  # deserialized with the matching archiver
```

### HuggingFace Models

```python
from transformers import AutoModelForImageClassification
from mindtrace.registry import Registry

registry = Registry("/models")

model = AutoModelForImageClassification.from_pretrained("google/vit-base-patch16-224")
registry.save("vit-classifier:v1", model)
loaded = registry.load("vit-classifier:v1")
```

PEFT handling: When saving a `PeftModel`, the archiver merges adapter weights into the base model (via `merge_and_unload()`) and saves the result as a clean `PreTrainedModel`. The original adapter config and weights are preserved in the `adapter/` subdirectory for provenance.

### HuggingFace Processors

```python
from transformers import AutoProcessor

processor = AutoProcessor.from_pretrained("google/vit-base-patch16-224")
registry.save("vit-processor:v1", processor)
loaded_processor = registry.load("vit-processor:v1")
```

### ONNX Models

```python
import onnx

model = onnx.load("exported_model.onnx")
registry.save("detector-onnx:v1", model)
loaded = registry.load("detector-onnx:v1")  # returns onnx.ModelProto
```

### timm Models

The timm archiver is not auto-registered against `nn.Module` (which would overwrite the generic PyTorch materializer). Register it explicitly or pass `materializer=TimmModelArchiver`.

```python
import timm
from mindtrace.models.archivers.timm.timm_model_archiver import TimmModelArchiver

model = timm.create_model("efficientnet_b0", pretrained=True, num_classes=10)

# Option 1: explicit materializer
registry.save("effnet:v1", model, materializer=TimmModelArchiver)

# Option 2: register for your specific type first
Registry.register_default_materializer(type(model), TimmModelArchiver)
registry.save("effnet:v1", model)

loaded = registry.load("effnet:v1")
```

### Ultralytics YOLO

```python
from ultralytics import YOLO

model = YOLO("yolov8n.pt")
model.train(data="coco128.yaml", epochs=5)
registry.save("yolo-detector:v1", model)
loaded = registry.load("yolo-detector:v1")
```

### Ultralytics SAM

```python
from ultralytics import SAM

model = SAM("sam2.1_b.pt")
registry.save("sam-segmenter:v1", model)
loaded = registry.load("sam-segmenter:v1")
```

## Registration Order and Dispatch

The Registry resolves archivers by walking the MRO of the object being saved. More specific types win over general ones.

| Model type | Archiver | Auto-registered |
|-----------|----------|-----------------|
| `PreTrainedModel` | `HuggingFaceModelArchiver` | Yes |
| `PeftModel` | `HuggingFaceModelArchiver` | Yes |
| `ProcessorMixin` / `PreTrainedTokenizerBase` | `HuggingFaceProcessorArchiver` | Yes |
| `onnx.ModelProto` | `OnnxModelArchiver` | Yes |
| `ultralytics.YOLO` | `YoloArchiver` | Yes |
| `ultralytics.YOLOWorld` | `YoloArchiver` | Yes |
| `ultralytics.YOLOE` | `YoloEArchiver` | Yes |
| `ultralytics.SAM` | `SamArchiver` | Yes |
| timm models (`nn.Module`) | `TimmModelArchiver` | No (explicit) |

## Dependencies

Each archiver guards its framework import. You only need to install the libraries for the model types you use.

| Archiver | Required package |
|----------|-----------------|
| HuggingFace model/processor | `transformers` (+ `peft` for LoRA) |
| ONNX | `onnx` |
| timm | `timm` |
| Ultralytics (YOLO/SAM) | `ultralytics` |

All archivers also depend on `zenml` for artifact type definitions and the `mindtrace.registry` package for the `Archiver` base class.

## API Reference

Archivers are not typically imported directly. They register themselves at import time and the Registry dispatches to them automatically.

```python
# Trigger registration (happens on any mindtrace.models import)
import mindtrace.models

# For explicit materializer usage
from mindtrace.models.archivers.huggingface.hf_model_archiver import HuggingFaceModelArchiver
from mindtrace.models.archivers.huggingface.hf_processor_archiver import HuggingFaceProcessorArchiver
from mindtrace.models.archivers.onnx.onnx_model_archiver import OnnxModelArchiver
from mindtrace.models.archivers.timm.timm_model_archiver import TimmModelArchiver
from mindtrace.models.archivers.ultralytics.yolo_archiver import YoloArchiver
from mindtrace.models.archivers.ultralytics.yoloe_archiver import YoloEArchiver
from mindtrace.models.archivers.ultralytics.sam_archiver import SamArchiver
```

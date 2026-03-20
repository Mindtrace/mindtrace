# mindtrace.models.archivers

ML model serialization and deserialization for the mindtrace Registry.
Each archiver handles a specific model framework (HuggingFace, timm, Ultralytics,
ONNX) and self-registers with the Registry at import time so that
`registry.save()` and `registry.load()` automatically select the correct
serialization strategy based on the model type.

```python
# Archivers register themselves when mindtrace.models is imported.
# You do not need to import archivers directly -- the Registry
# dispatches to the correct one based on isinstance checks.
from mindtrace.registry import Registry

registry = Registry("/path/to/registry")
registry.save("my-model:v1", model)       # archiver selected automatically
loaded = registry.load("my-model:v1")     # deserialized with the same archiver
```

---

## How self-registration works

When `mindtrace.models.archivers` is imported, the package-level
`register_ml_archivers()` function imports each archiver module. Each module
calls `Registry.register_default_materializer(ModelType, ArchiverClass)` at
module scope, which teaches the Registry how to serialize that model type.

Registration is guarded by `try/except ImportError` so missing optional
dependencies (e.g. `transformers`, `ultralytics`, `onnx`) do not prevent
the rest of the framework from loading.

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

---

## Archiver classes

### HuggingFaceModelArchiver

Handles all `PreTrainedModel` subclasses and PEFT/LoRA-wrapped models.

**Serialization format:**
- `config.json` + `pytorch_model.bin` or `model.safetensors` (standard HF layout)
- `adapter/` directory with PEFT config and weights (when applicable)

**PEFT handling:** When saving a `PeftModel`, the archiver merges adapter
weights into the base model (via `merge_and_unload()`) and saves the result as
a clean `PreTrainedModel`. The original adapter config and weights are preserved
in the `adapter/` subdirectory for provenance. On load, if the adapter was
already merged, re-injection is skipped.

```python
from transformers import AutoModelForImageClassification
from mindtrace.registry import Registry

registry = Registry("/models")

# Save
model = AutoModelForImageClassification.from_pretrained("google/vit-base-patch16-224")
registry.save("vit-classifier:v1", model)

# Load
loaded = registry.load("vit-classifier:v1")
```

### HuggingFaceProcessorArchiver

Handles HuggingFace processors, tokenizers, image processors, and feature
extractors (`ProcessorMixin`, `PreTrainedTokenizerBase`, `ImageProcessingMixin`,
`FeatureExtractionMixin`).

```python
from transformers import AutoProcessor
from mindtrace.registry import Registry

registry = Registry("/models")

processor = AutoProcessor.from_pretrained("google/vit-base-patch16-224")
registry.save("vit-processor:v1", processor)
loaded_processor = registry.load("vit-processor:v1")
```

### OnnxModelArchiver

Handles `onnx.ModelProto` instances.

**Serialization format:**
- `model.onnx` -- the ONNX model file
- `metadata.json` -- opset version, producer info, input/output names

```python
import onnx
from mindtrace.registry import Registry

registry = Registry("/models")

model = onnx.load("exported_model.onnx")
registry.save("detector-onnx:v1", model)
loaded = registry.load("detector-onnx:v1")  # returns onnx.ModelProto
```

### TimmModelArchiver

Handles models created with `timm.create_model()`. Identified by the presence
of `pretrained_cfg` or `default_cfg` attributes.

**Serialization format:**
- `config.json` -- architecture name, num_classes, pool type, drop rate
- `model.pt` -- PyTorch state_dict

**Note:** The timm archiver is not auto-registered against `nn.Module` (which
would overwrite the generic PyTorch materializer). Register it explicitly for
your model type, or pass `materializer=TimmModelArchiver` to `registry.save()`.

```python
import timm
from mindtrace.registry import Registry
from mindtrace.models.archivers.timm.timm_model_archiver import TimmModelArchiver

registry = Registry("/models")

model = timm.create_model("efficientnet_b0", pretrained=True, num_classes=10)

# Option 1: explicit materializer
registry.save("effnet:v1", model, materializer=TimmModelArchiver)

# Option 2: register for your specific type first
Registry.register_default_materializer(type(model), TimmModelArchiver)
registry.save("effnet:v1", model)

loaded = registry.load("effnet:v1")
```

### YoloArchiver

Handles `ultralytics.YOLO` and `ultralytics.YOLOWorld` models.

**Serialization format:** `model.pt` inside the artifact directory.

Includes fallback handling for pre-PyTorch-2.6 checkpoints that fail with
`weights_only=True` by temporarily patching `torch.load`.

```python
from ultralytics import YOLO
from mindtrace.registry import Registry

registry = Registry("/models")

model = YOLO("yolov8n.pt")
model.train(data="coco128.yaml", epochs=5)
registry.save("yolo-detector:v1", model)

loaded = registry.load("yolo-detector:v1")  # returns ultralytics.YOLO
```

### YoloEArchiver

Handles `ultralytics.YOLOE` (YOLO with Embeddings) models.

```python
from ultralytics import YOLOE
from mindtrace.registry import Registry

registry = Registry("/models")

model = YOLOE("yoloe-v8s.pt")
registry.save("yoloe:v1", model)
loaded = registry.load("yoloe:v1")
```

### SamArchiver

Handles `ultralytics.SAM` models (SAM and SAM2 variants). Identifies the
architecture variant by parameter count and encodes it in the filename so the
correct model is rebuilt on load.

**Supported variants:** `sam_b`, `sam_l`, `sam2_t`, `sam2_s`, `sam2_b`,
`sam2_l`, `sam2.1_t`, `sam2.1_s`, `sam2.1_b`, `sam2.1_l`.

```python
from ultralytics import SAM
from mindtrace.registry import Registry

registry = Registry("/models")

model = SAM("sam2.1_b.pt")
registry.save("sam-segmenter:v1", model)
loaded = registry.load("sam-segmenter:v1")
```

---

## Registration order and dispatch

The Registry resolves archivers by walking the MRO of the object being saved.
More specific types win over general ones:

| Model type | Archiver | Auto-registered |
|---|---|---|
| `PreTrainedModel` | `HuggingFaceModelArchiver` | Yes |
| `PeftModel` | `HuggingFaceModelArchiver` | Yes |
| `ProcessorMixin` / `PreTrainedTokenizerBase` | `HuggingFaceProcessorArchiver` | Yes |
| `onnx.ModelProto` | `OnnxModelArchiver` | Yes |
| `ultralytics.YOLO` | `YoloArchiver` | Yes |
| `ultralytics.YOLOWorld` | `YoloArchiver` | Yes |
| `ultralytics.YOLOE` | `YoloEArchiver` | Yes |
| `ultralytics.SAM` | `SamArchiver` | Yes |
| timm models (`nn.Module`) | `TimmModelArchiver` | No (explicit) |

---

## Dependencies

Each archiver guards its framework import. You only need to install the
libraries for the model types you use:

| Archiver | Required package |
|---|---|
| HuggingFace model/processor | `transformers` (+ `peft` for LoRA) |
| ONNX | `onnx` |
| timm | `timm` |
| Ultralytics (YOLO/SAM) | `ultralytics` |

All archivers also depend on `zenml` for artifact type definitions and the
`mindtrace.registry` package for the `Archiver` base class.

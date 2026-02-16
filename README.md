[![PyPI version](https://img.shields.io/pypi/v/mindtrace)](https://pypi.org/project/mindtrace/)
[![License](https://img.shields.io/pypi/l/mindtrace)](https://github.com/mindtrace/mindtrace/blob/main/LICENSE)
[![Downloads](https://static.pepy.tech/badge/mindtrace)](https://pepy.tech/projects/mindtrace)

# Mindtrace

A modular Python framework for building ML infrastructure: microservices, artifact registries, job orchestration, hardware integrations, and more.

📖 [Docs](https://mindtrace.github.io/mindtrace/) · 💡 [Samples](samples/) · 🤝 [Contributing](CONTRIBUTING.md)

## 📦 Installation

```bash
pip install mindtrace
# or
uv add mindtrace
```

Or install only what you need:

```bash
pip install mindtrace-services  # Microservices
pip install mindtrace-registry  # Artifact storage
pip install mindtrace-cluster   # Distributed workers
```

## 🚀 Getting Started

### Config & Logging

```python
from mindtrace.core import Mindtrace

class MyProcessor(Mindtrace):
    def run(self):
        # self.config and self.logger are provided automatically
        self.logger.error(f"Cache dir: {self.config.MINDTRACE_DIR_PATHS.ROOT}")

processor = MyProcessor()
processor.run()
# [2026-01-08 10:39:42] ERROR: MyProcessor: Cache dir: ~/.cache/mindtrace
```

### Deploy a Microservice

```python
from mindtrace.services.samples.echo_service import EchoService

# Launch service and get auto-generated client
client = EchoService.launch(port=8080)

result = client.echo(message="Hello, world!")
print(result.echoed)  # "Hello, world!"

client.shutdown()
```

Define your own service (must be in an importable module):

```python
# mypackage/predictor.py
from pydantic import BaseModel
from mindtrace.services import Service
from mindtrace.core import TaskSchema

class PredictInput(BaseModel):
    text: str

class PredictOutput(BaseModel):
    label: str
    confidence: float

predict_schema = TaskSchema(
    name="predict",
    input_schema=PredictInput,
    output_schema=PredictOutput,
)

class PredictorService(Service):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.add_endpoint("predict", self.predict, schema=predict_schema)

    def predict(self, payload: PredictInput) -> PredictOutput:
        return PredictOutput(label="positive", confidence=0.95)
```

### Save & Load Artifacts

```python
from mindtrace.registry import Registry
import numpy as np

registry = Registry()

# Save anything: arrays, datasets, configs, dicts
embeddings = np.random.rand(100, 768).astype(np.float32)
registry.save("data:embeddings:v1", embeddings)

# Load it back (with automatic versioning)
loaded = registry.load("data:embeddings:v1")
print(f"Loaded: {loaded.shape}, {loaded.dtype}")
# Loaded: (100, 768), float32
```

### Reactive State with Observables

```python
from mindtrace.core import ObservableContext

@ObservableContext(vars=["status", "progress"])
class Pipeline:
    def __init__(self):
        self.status = "idle"
        self.progress = 0

def on_change(source, var, old, new):
    print(f"{var}: {old} → {new}")

pipeline = Pipeline()
pipeline.subscribe(on_change, "context_updated")

pipeline.status = "running"   # prints: status: idle → running
pipeline.progress = 50        # prints: progress: 0 → 50
```

## 📚 Modules

| Module | Description |
|--------|-------------|
| [`core`](mindtrace/core) | Config, logging, observables, base classes |
| [`services`](mindtrace/services) | Microservice framework with auto-generated clients |
| [`registry`](mindtrace/registry) | Versioned artifact storage (models, datasets, configs) |
| [`database`](mindtrace/database) | Redis & MongoDB ODM with async support |
| [`cluster`](mindtrace/cluster) | Distributed worker orchestration |
| [`jobs`](mindtrace/jobs) | Job schemas and execution backends |
| [`hardware`](mindtrace/hardware) | Camera, PLC, and sensor integrations |
| [`datalake`](mindtrace/datalake) | Query and manage datasets, models, labels, and datums |
| [`models`](mindtrace/models) | Model definitions, inference, and leaderboards |
| [`storage`](mindtrace/storage) | Cloud storage interfaces (GCS, S3) |
| [`automation`](mindtrace/automation) | Pipeline orchestration and Label Studio integration |
| [`ui`](mindtrace/ui) | UI components and visualization |
| [`apps`](mindtrace/apps) | End-user applications and demos |

## 🏗️ Layered Architecture

Modules are organized into levels based on dependency direction. Each layer only depends on modules in lower levels.

| Level | Modules |
|-------|---------|
| **1. Foundation** | `core` |
| **2. Core Consumers** | `jobs`, `registry`, `database`, `services`, `storage`, `ui` |
| **3. Infrastructure** | `hardware`, `cluster`, `datalake`, `models` |
| **4. Automation** | `automation` |
| **5. Applications** | `apps` |

## 📖 Documentation

- [Full Documentation](https://mindtrace.github.io/mindtrace/)
- [Samples](samples/)
- [Contributing](CONTRIBUTING.md)

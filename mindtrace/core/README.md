[![PyPI version](https://img.shields.io/pypi/v/mindtrace-core)](https://pypi.org/project/mindtrace-core/)
[![License](https://img.shields.io/pypi/l/mindtrace-core)](https://github.com/mindtrace/mindtrace/blob/main/mindtrace/core/LICENSE)
[![Downloads](https://static.pepy.tech/badge/mindtrace-core)](https://pepy.tech/projects/mindtrace-core)

# Mindtrace Core

The `Core` module provides the foundational abstractions, configuration, logging, observability, typing, and utility helpers used across the Mindtrace ecosystem.

## Features

- **Base abstractions** with `Mindtrace`, `MindtraceABC`, and shared metaclass behavior
- **Configuration management** with `Config` and `CoreConfig`
- **Task typing** with `TaskSchema`
- **Logging and operation tracking** with standard and structured logging support
- **Observability primitives** with `EventBus`, `ObservableContext`, and `ContextListener`
- **Shared utility helpers** for dynamic loading, networking, timing, hashing, and metrics

## Quick Start

```python
from pydantic import BaseModel

from mindtrace.core import Mindtrace, TaskSchema, ifnone


class EchoInput(BaseModel):
    message: str


class EchoOutput(BaseModel):
    echoed: str


echo_task = TaskSchema(
    name="echo",
    input_schema=EchoInput,
    output_schema=EchoOutput,
)


class EchoComponent(Mindtrace):
    def echo(self, payload: EchoInput) -> EchoOutput:
        return EchoOutput(echoed=ifnone(payload.message, ""))


component = EchoComponent()
print(component.echo(EchoInput(message="Hello")))
print(component.config.MINDTRACE_DIR_PATHS.TEMP_DIR)
component.logger.info("Core component ready")
```

This example shows the typical role of `mindtrace-core`: it gives you a common base class, typed task contracts, configuration access, logging, and small utility helpers that other Mindtrace modules build on.

## Mindtrace

`Mindtrace` is the main base class for shared Mindtrace components. It provides:

- a consistent logger on both instances and classes
- access to `CoreConfig`
- context-manager support
- the `autolog()` decorator for automatic execution logging

Example:

```python
from mindtrace.core import Mindtrace


class DataProcessor(Mindtrace):
    def process(self, values: list[int]) -> list[int]:
        self.logger.info("Processing values")
        return [value * 2 for value in values]


with DataProcessor() as processor:
    print(processor.process([1, 2, 3]))
```

If you need an abstract base class with the same Mindtrace behavior, use `MindtraceABC`.

## Config

`Config` is the general-purpose configuration container in `mindtrace-core`. Use it when you want a flexible config object built from your own dictionaries, Pydantic models, or Pydantic settings objects.

It supports:

- dict-style access
- attribute-style access
- environment-variable overrides
- masking of secret fields by default
- cloning and JSON save/load helpers

`CoreConfig` uses the same underlying configuration system, but starts from Mindtrace’s standard core settings first and then layers your overrides on top.

In practice:

- use `Config` for generic application or component configuration
- use `CoreConfig` when you want the normal Mindtrace core sections already present, such as `MINDTRACE_DIR_PATHS`, `MINDTRACE_DEFAULT_HOST_URLS`, and `MINDTRACE_MCP`

Example with `Config`:

```python
from mindtrace.core import Config


config = Config(
    {
        "MY_APP": {
            "DEBUG": "true",
            "CACHE_DIR": "~/my-app-cache",
        }
    }
)

print(config.MY_APP.DEBUG)
print(config.MY_APP.CACHE_DIR)
```

Example with `CoreConfig`:

```python
from mindtrace.core import CoreConfig


config = CoreConfig(
    {
        "MY_APP": {
            "DEBUG": "true",
        }
    }
)

# Your own settings are still present
print(config.MY_APP.DEBUG)

# But CoreConfig also includes the standard Mindtrace core sections
print(config.MINDTRACE_DIR_PATHS.TEMP_DIR)
print(config.MINDTRACE_DEFAULT_HOST_URLS.SERVICE)
```

## TaskSchema

`TaskSchema` is the small but important typed contract used across the Mindtrace ecosystem. It describes:

- the task name
- the input model
- the output model

This is especially useful in higher-level packages such as `mindtrace-services`, where the same schema is used for endpoint validation and client generation.

Example:

```python
from pydantic import BaseModel

from mindtrace.core import TaskSchema


class SummarizeInput(BaseModel):
    text: str


class SummarizeOutput(BaseModel):
    summary: str


summarize_task = TaskSchema(
    name="summarize",
    input_schema=SummarizeInput,
    output_schema=SummarizeOutput,
)
```

## Logging

`mindtrace-core` provides both standard logging and structured logging support.

### Standard logger

Use `get_logger()` when you want a ready-to-use logger with Mindtrace defaults.

```python
from mindtrace.core.logging.logger import get_logger


logger = get_logger("core.example")
logger.info("Logger configured")
```

### Structured logger

If enabled, the same logging helpers can produce structured logs using `structlog`.

```python
from mindtrace.core.logging.logger import get_logger


logger = get_logger(
    "core.example",
    use_structlog=True,
    structlog_bind={"service": "demo"},
)
logger.info("Structured log event", user_id="123")
```

### `Mindtrace.autolog`

Use `Mindtrace.autolog()` when you want to automatically log function execution, completion, and failures.

```python
from mindtrace.core import Mindtrace


class DataProcessor(Mindtrace):
    @Mindtrace.autolog()
    def double(self, values: list[int]) -> list[int]:
        return [value * 2 for value in values]
```

### `track_operation`

Use `track_operation()` when you want explicit operation-level logging, including duration and optional system metrics.

```python
from mindtrace.core.logging.logger import track_operation


@track_operation("load_data")
def load_data() -> list[int]:
    return [1, 2, 3]
```

## Observables

The observables utilities support lightweight eventing and reactive state updates.

## `EventBus`

`EventBus` is a simple publish-subscribe mechanism for dispatching events by name.

```python
from mindtrace.core import EventBus


bus = EventBus()


def handler(**kwargs):
    print(kwargs)


bus.subscribe(handler, "data_loaded")
bus.emit("data_loaded", records=3)
bus.unsubscribe(handler, "data_loaded")
```

## `ObservableContext`

`ObservableContext` is a class decorator that turns selected attributes into observable fields.

```python
from mindtrace.core import ObservableContext


@ObservableContext(vars=["status"])
class JobContext:
    def __init__(self):
        self.status = "created"


ctx = JobContext()
ctx.status = "running"
```

## `ContextListener`

`ContextListener` is a Mindtrace-aware helper for listening to observable context changes.

```python
from mindtrace.core import ContextListener, ObservableContext


@ObservableContext(vars={"progress": int})
class JobContext:
    def __init__(self):
        self.progress = 0


ctx = JobContext()
ctx.subscribe(ContextListener(autolog=["progress"]))
ctx.progress = 50
```

## Utility Helpers

`mindtrace-core` also provides a collection of lower-level helpers used across the ecosystem.

### Dynamic loading

```python
from mindtrace.core import instantiate_target


instance = instantiate_target("my_package.my_module.MyClass", name="demo")
```

### Network helpers

```python
from mindtrace.core import get_free_port, wait_for_service


port = get_free_port(start_port=8000, end_port=8100)
print(port)

# Wait for something to start listening on that port
wait_for_service("localhost", port, timeout=5.0)
```

### Timers and timeout helpers

```python
from mindtrace.core import Timeout


def eventually_ready():
    return "ready"


timeout = Timeout(timeout=5)
print(timeout.run(eventually_ready))
```

### Hashing and metrics

```python
from mindtrace.core import SystemMetricsCollector, compute_dir_hash


collector = SystemMetricsCollector()
print(collector())
print(compute_dir_hash("./some-directory"))
```

## Examples

See these examples and related docs in the repo for more end-to-end reference:

- [Core echo task sample](mindtrace/core/mindtrace/core/samples/echo_task.py)
- [Core configuration examples](samples/core/config)
- [Core logging / autolog examples](samples/core/logging)

## Testing

If you are working in the full Mindtrace repo, run tests for this module specifically:

```bash
git clone https://github.com/Mindtrace/mindtrace.git && cd mindtrace
uv sync --dev --all-extras
```

```bash
# Run the core test suite
ds test: core

# Run only unit tests for core
ds test: --unit core
```

## Practical Notes and Caveats

- `CoreConfig` includes Mindtrace’s default core settings; plain `Config` is the more generic configuration container.
- Secret configuration values are masked by default; use explicit secret access helpers when you need the real value.
- `TaskSchema` is a typed contract, not an execution engine by itself.
- `Mindtrace.autolog()` and `track_operation()` overlap conceptually, but they are useful at different levels of abstraction.
- Many helpers in `core` are intentionally low-level building blocks; the README should help you discover them, while the code docs remain the detailed reference.

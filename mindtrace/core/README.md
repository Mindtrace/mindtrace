[![PyPI version](https://img.shields.io/pypi/v/mindtrace-core)](https://pypi.org/project/mindtrace-core/)
[![License](https://img.shields.io/pypi/l/mindtrace-core)](https://github.com/mindtrace/mindtrace/blob/main/mindtrace/core/LICENSE)
[![Downloads](https://static.pepy.tech/badge/mindtrace-core)](https://pepy.tech/projects/mindtrace-core)

# Mindtrace Core

The `Core` module provides the foundational abstractions, configuration, logging, observability, typing, and utility helpers used across the Mindtrace ecosystem.

## Features

- **Base abstractions** with `Mindtrace` and `MindtraceABC`
- **Configuration management** with a single `Config` (a `pydantic_settings.BaseSettings` subclass)
- **Task typing** with `TaskSchema`
- **Logging and operation tracking** with standard and structured logging support
- **Observability primitives** with `EventBus`, `ObservableContext`, and `ContextListener`
- **Minimal NATS shim** with `connect()`, Pydantic encode/decode, and scoped helpers
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

- a consistent logger on both instances and classes (`self.logger` / `cls.logger`)
- access to the shared `Config` (`self.config` / `cls.config`)
- context-manager support

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

`Config` is the shared configuration container in `mindtrace-core`. It is a `pydantic_settings.BaseSettings` subclass with the standard Mindtrace sections (`MINDTRACE_DIR_PATHS`, `MINDTRACE_DEFAULT_HOST_URLS`, `MINDTRACE_API_KEYS`, ...) declared as typed fields.

Values are loaded from (highest to lowest precedence):

1. Constructor kwargs
2. Environment variables (`SECTION__KEY` delimiter)
3. `.env` file
4. `config.ini` bundled with the package

Features:

- attribute-style access (`config.MINDTRACE_DIR_PATHS.TEMP_DIR`)
- dict-style access (`config["MINDTRACE_DIR_PATHS"]["TEMP_DIR"]`)
- `~` expansion on string fields
- secret masking on `repr()`; reveal with `get_secret(...)` or `model_dump_json()`

```python
from mindtrace.core import Config


config = Config()

print(config.MINDTRACE_DIR_PATHS.TEMP_DIR)
print(config["MINDTRACE_DEFAULT_HOST_URLS"]["SERVICE"])

# Reveal a single secret
api_key = config.get_secret("MINDTRACE_API_KEYS", "OPENAI")
```

Override via environment variable (most common):

```bash
export MINDTRACE_DEFAULT_HOST_URLS__SERVICE=http://custom:8080
```

`Config()` will pick that up automatically.

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

By default all loggers write to a single rotating file at `~/.cache/mindtrace/logs/mindtrace.log` (plus the console stream). To also get a per-module file at `logs/modules/<logger-name>.log`, set `MINDTRACE_LOGGER__PER_MODULE_FILES=true` — records are then written to both the unified file and the per-module one.

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

### `track_operation`

Use `track_operation()` when you want explicit operation-level logging around a specific unit of work. It is useful for things like:

- measuring how long an operation took
- attaching structured context such as a batch ID or file name
- recording optional system metrics alongside the operation
- producing start / completed / failed log events in a consistent format

```python
from mindtrace.core.logging.logger import track_operation


@track_operation("load_data", include_system_metrics=True, dataset="train")
def load_data() -> list[int]:
    return [1, 2, 3]
```

With this pattern, the logs can include fields such as:

- the operation name
- whether it started, completed, or failed
- duration / duration_ms
- any extra context you bound, such as `dataset="train"`
- optional system metrics, such as CPU or memory usage

That makes `track_operation()` a good fit when you care about observability of a specific workflow step, not just generic function logging.

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

## NATS

`mindtrace.core.nats` is a tiny shim over [`nats-py`](https://nats-io.github.io/nats.py/). It contributes exactly two ideas:

1. `async with connect(...)` opens a NATS connection and drains on exit.
2. `encode(payload)` / `decoded(msg, model)` handle Pydantic ⇄ JSON at the edges.

Everything else — `nc.subscribe`, `nc.jetstream()`, `js.pull_subscribe`, `js.key_value`, `msg.ack`/`nak`/`term`, etc. — is plain `nats-py`. Learn it from the upstream docs; the names match.

### Pub/sub

```python
import asyncio
from pydantic import BaseModel
from mindtrace.core.nats import connect, decoded, publish


class Greeting(BaseModel):
    name: str


async def main():
    async with connect() as nc:
        sub = await nc.subscribe("greet")
        try:
            await publish(nc, "greet", Greeting(name="world"))
            msg = await sub.next_msg(timeout=2.0)
            print(decoded(msg, Greeting))  # Greeting(name='world')
        finally:
            await sub.unsubscribe()


asyncio.run(main())
```

### Request/reply

```python
from mindtrace.core.nats import request

reply = await request(nc, "square", Q(n=9), timeout=2.0, model=A)
```

### Long-running consumer

The shim doesn't own task lifecycle — you do. Run the consumer under `asyncio.TaskGroup` so exceptions propagate naturally:

```python
async def consume(nc):
    sub = await nc.subscribe("jobs.*")
    try:
        while True:
            msg = await sub.next_msg(timeout=5.0)
            try:
                await process(decoded(msg, Job))
            except Exception:
                logger.exception("job failed")

    finally:
        await sub.unsubscribe()


async with connect() as nc, asyncio.TaskGroup() as tg:
    tg.create_task(consume(nc))
    await asyncio.sleep(10)  # let it run; group propagates any failure
```

### JetStream, KV, Object Store

Use `nc.jetstream()` and the native nats-py methods (`add_stream`, `pull_subscribe`, `key_value`, `object_store`, …). For ephemeral test resources, the shim provides three `scoped_*` helpers that create on enter and destroy on exit:

```python
from mindtrace.core.nats import scoped_kv

async with connect() as nc:
    async with scoped_kv(nc.jetstream(), "settings") as kv:
        await kv.put("greeting", b"hello")
        entry = await kv.get("greeting")
        print(entry.value)
```

`scoped_stream(js, name, subjects=[...])` and `scoped_object_store(js, bucket)` are symmetric. Note `kv.get(...)` raises `nats.js.errors.KeyNotFoundError` on a missing key — handle it the way you'd handle any nats-py error.

### Configuration

`connect()` forwards every kwarg to `nats.connect`, so pass `servers=[...]`, `user=...`, etc. directly:

```python
from mindtrace.core.nats import connect

async with connect(servers=["nats://broker:4222"], user="svc", password=os.environ["NATS_PASS"]) as nc:
    ...
```

For env-driven config, use `connect_from_env()` — it reads `MINDTRACE_NATS__URLS`, `__USER`, `__PASSWORD`, `__TOKEN`:

```python
from mindtrace.core.nats import connect_from_env

async with connect_from_env() as nc:  # picks up MINDTRACE_NATS__URLS
    ...
```

TLS works out of the box for `tls://...` URLs (nats-py auto-builds the context). For mTLS, build a `ssl.SSLContext` and pass it via `connect(tls=ctx)`.

### Errors

All errors come from `nats-py` or `pydantic` and propagate as-is — there is no custom exception hierarchy. The names you'll see:

- `nats.errors.ConnectionClosedError` — method called after `connect()` has exited.
- `nats.errors.NoRespondersError` — `request(...)` to a subject with no live responders.
- `nats.errors.TimeoutError` / `asyncio.TimeoutError` — request, fetch, or drain windows expired.
- `nats.js.errors.KeyNotFoundError` — KV `get(key)` on a missing key.
- `pydantic.ValidationError` — `decoded(msg, Model)` on a payload that doesn't validate.

## Utility Helpers

`mindtrace-core` also provides a collection of lower-level helpers used across the ecosystem.

### Dynamic loading

```python
from mindtrace.core import instantiate_target


instance = instantiate_target(
    "my_package.my_module.MyClass",
    **{"config_path": "settings.json", "debug": True},
)
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
- [Core logging examples](samples/core/logging)
- [Core observables examples](samples/core/observables)
- [Core NATS samples](samples/core/nats)

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

- `Config` is a `pydantic_settings.BaseSettings`.
- Secret configuration values are masked on `repr()`; use `config.get_secret(...)` or `model_dump_json()` when you need the real value.
- `TaskSchema` is a typed contract, not an execution engine by itself.
- `track_operation()` attaches structured per-operation context (duration, start/completed/failed, system metrics).
- `mindtrace.core.nats` is async-only by design — the underlying `nats-py` is asyncio-native, and there is no sync facade.
- Many helpers in `core` are intentionally low-level building blocks; the README should help you discover them, while the code docs remain the detailed reference.

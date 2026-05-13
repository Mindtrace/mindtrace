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
- **Async-native NATS messaging** with `NatsClient`, JetStream, KV, and Object Store
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

## Messaging (NATS)

`mindtrace-core` ships an async-native NATS substrate built on `nats-py`. It's the distributed counterpart to `EventBus`: where `EventBus` is in-process pub/sub, `NatsClient` is a connection to a real NATS server and covers pub/sub, request/reply, durable JetStream streams, KV buckets, and Object Store.

The surface is intentionally Pydantic-aware — payloads accept `bytes`, `str`, `dict`, or any `pydantic.BaseModel` (auto-JSON-encoded), and you can decode received messages into a model by passing `model=`.

### Pub/sub

```python
import asyncio

from pydantic import BaseModel

from mindtrace.core import NatsClient


class Greeting(BaseModel):
    name: str


async def main():
    async with NatsClient.connect() as nc:
        async with nc.subscribe("greet", model=Greeting) as sub:
            await nc.publish("greet", Greeting(name="world"))
            msg = await asyncio.wait_for(sub.__anext__(), timeout=2.0)
            print(msg.data)  # Greeting(name='world')


asyncio.run(main())
```

### Callback workers

For the "background worker" pattern, pass `handler=` to `subscribe`. The client runs your handler in a managed task and auto-acks on success / naks on exception (a no-op on core NATS, meaningful for JetStream).

```python
async def handle(msg):
    process(msg.data)


async with nc.subscribe("jobs.*", handler=handle, model=Job) as worker:
    await asyncio.sleep(10)  # run for 10s, then drain on exit
```

### Request/reply

```python
reply = await nc.request("square", Q(n=9), timeout=2.0, model=A)
```

### JetStream, KV, Object Store

`nc.jetstream()` returns a context with `add_stream` / `delete_stream` / `scoped_stream`, plus `pull_subscribe` and `push_subscribe`. The convenience methods `nc.add_stream` / `nc.scoped_stream` are shortcuts for the JetStream context. KV and Object Store buckets are accessed via `nc.kv(...)` / `nc.create_kv(...)` (and the symmetric `scoped_kv` / `scoped_object_store` helpers that create on enter and destroy on exit).

```python
async with nc.scoped_kv("settings") as kv:
    await kv.put("greeting", "hello")
    print(await kv.get("greeting"))
    # KV.get raises nats.js.errors.KeyNotFoundError on a missing key
    # unless you pass `default=`:
    print(await kv.get("missing", default=None))  # → None
```

JetStream `pull_subscribe` has both iterator and worker forms — pass `handler=` to get a managed fetch loop with auto-ack/nak, `batch=` and `fetch_timeout=` to tune the polling cadence. `push_subscribe` mirrors the same two shapes.

KV `watch()` / `history()` (the streaming-update features of NATS KV) are not surfaced yet — drop to `kv.raw.watch(...)` if you need them.

### Configuration

Defaults come from `MINDTRACE_NATS__*` env vars (nested-delimiter `__`, matching `CoreConfig`'s convention):

- `MINDTRACE_NATS__URLS` — comma-separated server URLs (cluster failover supported).
- `MINDTRACE_NATS__USER` / `__PASSWORD` / `__TOKEN` / `__USER_CREDENTIALS` / `__NKEYS_SEED` — auth.
- `MINDTRACE_NATS__TLS` and `MINDTRACE_NATS__TLS_CA_FILE` / `__TLS_CERT_FILE` / `__TLS_KEY_FILE` — TLS.

Or pass settings directly: `NatsClient.connect(urls=[...], settings=NatsSettings(...))`.

### Observability

`nc.health()` returns a typed `NatsHealth` snapshot with the connected URL, full server list, `stats` (in/out msg + byte counters from nats-py), and any `last_error` (plus `last_error_at` UTC timestamp) captured by the wrapped `error_cb`. Pydantic publishes auto-stamp `Content-Type: application/json` in headers so non-Python consumers can inspect the wire format; any headers you pass through (including `traceparent`) are forwarded verbatim.

### Errors you'll catch

The library is intentionally thin — most errors come from `nats-py` or `pydantic` and propagate as-is. The names worth knowing:

- `mindtrace.core.NatsClientClosed` — any method called after the `connect()` async context manager has exited.
- `asyncio.TimeoutError` — `request(timeout=...)`, JetStream pull `fetch(timeout=...)`, and `drain` exceeding their windows.
- `nats.errors.NoRespondersError` — `request(...)` to a subject with no live responders.
- `nats.errors.TimeoutError` — JetStream-specific timeout (`fetch` raises this and the worker loop treats it as "no work yet" rather than fatal).
- `nats.js.errors.KeyNotFoundError` — `KeyValueHandle.get(key)` when the key is absent and no `default=` is supplied.
- `pydantic.ValidationError` — `model=`-typed decode of a payload that doesn't validate.

Worker forms (`subscribe(handler=...)`, `push_subscribe(handler=...)`, `pull_subscribe(handler=...)`) catch per-message handler exceptions and forward them to `on_error` without terminating the loop. A *fatal* loop exception (the message source itself raising) is captured on the `SubscriptionHandle` and re-raised when the async context manager exits — silent worker death is impossible.

### CLI

For quick ops smoke tests (uses the same `MINDTRACE_NATS__*` env vars; defaults to `nats://localhost:4222`):

```bash
uv run python -m mindtrace.core.messaging.nats publish my.subject 'hello'
uv run python -m mindtrace.core.messaging.nats publish my.subject '{"n":1}' --json
uv run python -m mindtrace.core.messaging.nats publish my.subject --file ./payload.bin
uv run python -m mindtrace.core.messaging.nats subscribe 'events.>' --count 5
uv run python -m mindtrace.core.messaging.nats request my.subject 'ping' --timeout 2.0
```

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
- [Core NATS messaging examples](samples/core/messaging)

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
- `NatsClient` is async-only by design — the underlying `nats-py` is asyncio-native, and there is no sync facade.
- Many helpers in `core` are intentionally low-level building blocks; the README should help you discover them, while the code docs remain the detailed reference.

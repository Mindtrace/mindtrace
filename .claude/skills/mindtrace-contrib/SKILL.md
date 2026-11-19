---
name: mindtrace-contrib
description: Use this skill before adding any contribution to the Mindtrace library. It defines all existing modules and their APIs, guides selection of the correct Mindtrace-native component for each task, enforces layered architecture boundaries, and flags known missing features and bugs. Invoke with /mindtrace-contrib.
version: 1.1.0
---

# Mindtrace Contribution — API & Module Reference

This skill covers **what exists and which component to use**. For workflow, branching, testing commands, PR process, and code quality rules, read `AGENTS.md` first.

This skill answers:
1. Which existing component should I use (or extend)?
2. What is already built so I do not duplicate it?
3. Where are the known gaps and bugs I should be aware of?

---

## 1. Module Map — What Exists and Where

### Layer 1: Foundation

**`mindtrace.core`** — used by every other module
- `Mindtrace` — base class. Gives `self.logger`, `self.config`, context-manager support. **All Mindtrace classes should subclass this.**
- `MindtraceABC` — same as above but abstract.
- `Config` — singleton pydantic-settings config. Access via `self.config` or `Config()`. Sections: `MINDTRACE_DIR_PATHS`, `MINDTRACE_DEFAULT_HOST_URLS`, `MINDTRACE_API_KEYS`.
- `TaskSchema(name, input_schema, output_schema)` — typed contract shared by services, jobs, and cluster.
- `EventBus` — pub/sub for in-process events.
- `ObservableContext` — class decorator that makes selected attributes observable.
- `ContextListener` — Mindtrace-aware observable subscriber.
- `get_logger(name)` / `track_operation(name)` — structured logging helpers.
- Utilities: `get_free_port`, `wait_for_service`, `Timeout`, `instantiate_target`, `SystemMetricsCollector`, `compute_dir_hash`, `ifnone`.

### Layer 2: Core Infrastructure

**`mindtrace.services`** — typed microservices
- `Service` — server base. Subclass it; call `self.add_endpoint(path, func, schema=TaskSchema(...))` to register endpoints. **Do not use raw FastAPI routers or Flask.**
- `ConnectionManager` — client base. Auto-generated from service endpoints. Override only when you need richer methods, retries, or auth.
- `Service.launch(host, port, wait_for_launch=True)` → `ConnectionManager` — spawns subprocess, returns typed client.
- `Service.connect(url)` → `ConnectionManager` — attaches to a running service.
- `add_endpoint(..., as_tool=True)` — also exposes the endpoint as an MCP tool automatically.
- `add_tool(name, func)` — MCP-only tool registration.
- `Gateway` + `ProxyConnectionManager` — route through a central gateway. Use these instead of writing your own proxy.
- Built-in lifecycle endpoints on every service: `status`, `heartbeat`, `shutdown`, `endpoints`, `server_id`, `pid_file`.
- Generated async methods: endpoint `echo` → `cm.echo()` + `await cm.aecho()`.

**`mindtrace.registry`** — versioned artifact storage
- `Registry(backend?)` — primary interface. `registry.save(name, obj)`, `registry.load(name)`, `registry["name"] = obj`, `registry["name"]`.
- Backends: `LocalRegistryBackend` (default), `S3RegistryBackend` (MinIO/AWS), `GCPRegistryBackend`.
- `Store` — multi-registry facade. Mount multiple registries; qualified keys `"mount/name"` target specific mounts.
- `registry.info()`, `registry.list_objects()`, `registry.list_versions()`, `registry.has_object()`.
- Version control: `version_objects=True` auto-increments; load with `version="latest"` or specific version.
- Exceptions: `RegistryObjectNotFound`, `RegistryVersionConflict`.

**`mindtrace.storage`** — raw object storage (lower level than Registry; used by Registry internally)
- `GCSStorageHandler` / `S3StorageHandler` — upload, download, delete, list, presigned URLs.
- `MinioStorageHandler` is an alias for `S3StorageHandler`.
- Result types: `Status`, `FileResult`, `StringResult`, `BatchResult`.
- Use **Registry** when you want versioning and materializers. Use **Storage** only when you need raw byte access to a bucket without Registry semantics.

**`mindtrace.database`** — ODM layer
- `UnifiedMindtraceODM` — recommended starting point; works across MongoDB and Redis.
- `MongoMindtraceODM` — MongoDB-specific, built on Beanie. Native async.
- `RedisMindtraceODM` — Redis-specific, built on redis-om. Native sync.
- `RegistryMindtraceODM` — Registry-backed ODM, no external DB needed. Limited query capability.
- Document models: `UnifiedMindtraceDocument`, `MindtraceDocument`, `MindtraceRedisDocument`.
- Operations: `insert` / `insert_async`, `get` / `get_async`, `update` / `update_async`, `all` / `all_async`, `find` / `find_async`.
- Multi-model mode: pass `unified_models={"user": User, "address": Address}`; access via `db.user.insert(...)`.
- Exceptions: `DocumentNotFoundError`, `DuplicateInsertError`.

**`mindtrace.jobs`** — typed job queues
- `JobSchema(name, input_schema, output_schema)` — alias of `TaskSchema`; use for queue/job types.
- `Orchestrator(backend)` — owns queues; `orchestrator.register(schema)`, `orchestrator.publish(queue, input_model)`.
- `Consumer` — subclass and implement `run(job_dict: dict) -> dict`.
- Backends: `LocalClient` (dev), `RedisClient`, `RabbitMQClient`.
- `job_from_schema(schema, input)` — create a `Job` instance.
- Queue types: `fifo` (default), `stack`, `priority` (local/Redis). RabbitMQ uses `max_priority` parameter.

### Layer 3: Higher-Level Systems

**`mindtrace.cluster`** — distributed job execution
- `ClusterManager` — control plane and Gateway. Single client entry point for job submission, status, worker management.
- `Node` — launches workers on machines.
- `Worker` — service + consumer. Subclass and implement `_run(job_dict) -> dict`.
- `ClusterManager.launch(host, port, wait_for_launch=True)` — standard launch pattern.
- Two routing modes:
  - **Direct endpoint**: `cluster.register_app(...)` then `cluster.register_job_to_endpoint(job_type, endpoint)` — synchronous HTTP.
  - **Orchestrator/worker queue**: `cluster.register_job_schema_to_worker_type(...)` — async RabbitMQ.
- DLQ: `cluster.get_dlq_jobs()`, `cluster.requeue_from_dlq(job_id)`, `cluster.discard_from_dlq(job_id)`.
- Built-in workers: `EchoWorker` (smoke test), `RunScriptWorker` (Docker or Git environments).
- External dependencies: RabbitMQ (queued jobs), Redis (status), MinIO/Registry (worker registry).

**`mindtrace.agents`** — LLM agents
- `MindtraceAgent(model, system_prompt, tools, toolset, history, callbacks)` — central runtime.
- `OpenAIProvider` / `OllamaProvider` / `GeminiProvider` — backend connectivity. **Use these; do not call OpenAI SDK directly.**
- `OpenAIChatModel(model_name, provider)` — model interface.
- Tool registration: pass `tools=[Tool(fn)]` or a `FunctionToolset`.
- `MCPToolset.from_http(url)` — connect to any MCP-capable Mindtrace service.
- `CompoundToolset(ts1, ts2, ...)` — merge toolsets.
- Tool filtering: `toolset.include(...)`, `toolset.exclude(...)`, `toolset.include_pattern(...)`.
- `AgentCallbacks(before_llm_call, after_tool_call)` — lifecycle hooks.
- History: `InMemoryHistory`; implement `AbstractHistoryStrategy` for custom backends.
- Memory: `MemoryToolset(JsonFileStore(...), namespace)` — exposes `save_memory`, `recall_memory`, `search_memory`, `forget_memory`, `list_memories` as agent tools.
- Streaming: `agent.run_stream_events(...)`, step iteration: `async with agent.iter(...) as steps`.
- Multi-agent: pass one agent as a tool into another's `tools=[]`.
- Distributed: `DistributedAgent(agent, task_queue=LocalTaskQueue() | RabbitMQTaskQueue(...))`.
- `agent.run_sync(...)` — no event loop needed.

**`mindtrace.hardware`** — industrial hardware
- Cameras: `Camera(name)` (sync), `AsyncCameraManager` (async + bandwidth), `CameraManagerService.launch(port)` (service layer).
- Stereo cameras: `StereoCamera`, `StereoCameraManager`, `StereoCameraService`.
- 3D scanners: `AsyncScanner3D.open(name)`, `Scanner3DService`.
- PLCs: `PLCManager`, `PLCManagerService`. Drivers: `LogixDriver`, `SLCDriver`, `CIPDriver`.
- Sensors: `AsyncSensor(name, backend, topic)`, `MQTTSensorBackend`. **HTTP and Serial backends are not yet implemented** (see Known Gaps).
- Camera name format: `"Backend:device_id"` (e.g., `"Basler:basler_camera_0"`, `"OpenCV:opencv_camera_0"`).
- Always use the service layer (`CameraManagerService`, etc.) for remote or distributed hardware access.
- Homography: `HomographyCalibrator`, `HomographyMeasurer` for pixel-to-world measurement.

**`mindtrace.datalake`** — data/annotation management
- `AsyncDatalake` / `Datalake` — core datalake interface.
- `DatalakeService` — FastAPI + MCP service wrapping `AsyncDatalake`. Launch with `DatalakeService.launch(...)`.
- `DataVault` / `AsyncDataVault` — save/load facade. Use `DataVault(datalake)` locally or `DataVault(cm)` over HTTP.
- Key task families: `objects.*`, `assets.*`, `collections.*`, `dataset_versions.*`, `replication.*`, `annotation_*`, `datums.*`.
- Depends on: `mindtrace.database` (structured records), `mindtrace.registry` (payloads).
- Do not define canonical datalake schemas inside `jobs` or `cluster`; datalake schemas belong here.

**`mindtrace.models`** — ML lifecycle
- `build_model(backbone_name, head_key, ...)` — assemble from 33 registered backbones + 6 head types.
- `build_model_from_hf(hf_model_id, head_key, ...)` — any HuggingFace vision model.
- `Trainer(model, loss_fn, optimizer, scheduler, callbacks)` — training loop with AMP, DDP, gradient accumulation.
- `ModelCard(name, version, task, registry)` — lifecycle management: DEV → STAGING → PRODUCTION → ARCHIVED.
- `EvaluationRunner(model, task, num_classes)` — orchestrate inference + metrics.
- Tracking: `MLflowTracker`, `WandBTracker`, `TensorBoardTracker`, `CompositeTracker`.
- Serving: `OnnxModelService`, `ModelService` base; endpoint `/predict`, `/info`.
- Archivers auto-register on `import mindtrace.models` — no explicit registration needed.
- `ModelService` extends `mindtrace.services.Service`. **Do not write a raw FastAPI app for model serving.**

---

## 2. Decision Guide — Which Module to Use

| Task | Use This | NOT This |
|------|----------|----------|
| Build a typed API / microservice | `mindtrace.services.Service` + `TaskSchema` | Raw FastAPI, Flask |
| Add MCP tool support to a service | `add_endpoint(..., as_tool=True)` or `add_tool(...)` | Custom FastMCP wiring |
| Store/load versioned artifacts | `mindtrace.registry.Registry` | Raw filesystem, pickle, custom S3 |
| Store/load raw bytes in GCS/S3 | `mindtrace.storage.GCSStorageHandler` / `S3StorageHandler` | boto3/google-cloud-storage directly |
| Document persistence | `mindtrace.database.*ODM` | Raw pymongo, redis-py, SQLAlchemy |
| Background / queue jobs | `mindtrace.jobs.Orchestrator` + `Consumer` | Celery, raw RabbitMQ, threading |
| Distributed workers across machines | `mindtrace.cluster.ClusterManager` + `Node` + `Worker` | Custom SSH scripts, manual RabbitMQ |
| LLM agent with tools | `mindtrace.agents.MindtraceAgent` | LangChain, raw OpenAI SDK |
| Connect agent to a running service | `MCPToolset.from_http(service_url)` | Custom REST client in the tool |
| Camera / scanner / PLC access | `mindtrace.hardware.*` | Direct SDK calls outside hardware module |
| Base class for any new class | `mindtrace.core.Mindtrace` or `MindtraceABC` | `object`, `ABC` directly |
| Configuration | `self.config` (from `Mindtrace`) | `os.environ`, `dotenv`, `argparse` |
| Logging | `self.logger` (from `Mindtrace`) | `print`, `logging.getLogger` directly |
| Manage ML model lifecycle | `mindtrace.models.ModelCard` | Custom metadata JSONs |
| ML experiment tracking | `mindtrace.models.MLflowTracker` etc. | Direct `mlflow.log_metric(...)` |
| Train a model | `mindtrace.models.Trainer` | Custom training loop from scratch |
| Serve an ML model | `mindtrace.models.ModelService` (extends `Service`) | Flask, raw ONNX serving scripts |
| Data + annotation management | `mindtrace.datalake.DatalakeService` / `DataVault` | Custom Mongo schemas |

### Architecture boundary rule
Imports must flow downward only:

```
core → storage, registry, database, services, jobs
storage → registry
registry → database, datalake
services → cluster, agents, hardware, datalake, models
jobs → cluster
cluster → automation
agents → automation
datalake → models (training data)
```

If your change creates a dependency that goes upward (e.g., `core` importing from `services`), move the shared abstraction **down** into `core` instead, or use a protocol/interface with dependency injection.

---

## 3. Known Gaps and Bugs (as of docs review)

Flag these before starting any related contribution. Verify current state by checking the relevant source files.

### Sensor HTTP and Serial backends — NOT IMPLEMENTED
- **Location**: `mindtrace/hardware/sensors/`
- **Status**: Hardware README explicitly marks HTTP and Serial sensor backends as "Planned".
- **Impact**: `AsyncSensor` only works with `MQTTSensorBackend`. Any contribution touching sensors must use MQTT or implement a new backend following the existing pattern.

### Cross-lake `metadata_only` import — intentionally blocked
- **Location**: `mindtrace/datalake/`
- **Status**: Cross-lake `metadata_only` import is rejected until unresolved-placeholder semantics are defined.
- **Impact**: Do not implement cross-lake metadata-only transfer; see `docs/datalake-v3-proposal.md` for the design context.

### Datalake V3 is in-progress
- **Location**: `mindtrace/datalake/`
- **Status**: V2 is the current working version. V3 entity model (Collection, Asset, StorageRef, etc.) is the design direction but not fully implemented.
- **Impact**: New datalake contributions should align with V3 design principles (see datalake README "Design principles" section) even when extending V2 code.

### `JobSchema` is an alias for `TaskSchema`
- **Location**: `mindtrace/jobs/__init__.py`
- **Status**: `JobSchema = TaskSchema`. The naming transition is incomplete.
- **Impact**: Use `JobSchema` in job-related code for intent clarity, but be aware they are the same class. Do not create a separate `JobSchema` implementation.

### `RegistryMindtraceODM` has limited query capability
- **Location**: `mindtrace/database/`
- **Status**: Intentionally simpler than MongoDB/Redis. No rich filter expressions.
- **Impact**: Do not add MongoDB-style queries to `RegistryMindtraceODM`; it is meant for simple key-value persistence.

### `add_endpoint` generates only POST routes
- **Location**: `mindtrace/services/`
- **Status**: All registered endpoints are POST by default. There is no documented GET endpoint registration.
- **Impact**: If a GET-style endpoint is needed, check the service source to confirm whether HTTP method overrides are supported before implementing one.

### `UnifiedMindtraceODM` multi-model mode calling restriction
- **Location**: `mindtrace/database/`
- **Status**: Calling `db.insert(...)` directly in multi-model mode raises `ValueError`. Must use `db.model_name.insert(...)`.
- **Impact**: Always check initialization mode before calling ODM methods directly.

### `DatalakeService` startup initialization is not automatic
- **Location**: `mindtrace/datalake/`
- **Status**: Initialization is lazy by default. Live processes must explicitly configure startup initialization and background helpers (e.g., upload-session reconciliation).
- **Impact**: Contributions that add background datalake operations must account for this; do not assume the service is fully initialized on import.

### `MinioStorageHandler` is a deprecated alias
- **Location**: `mindtrace/storage/`
- **Status**: `MinioStorageHandler = S3StorageHandler` is a backwards-compatible alias.
- **Impact**: Use `S3StorageHandler` in all new code. Do not add new functionality to `MinioStorageHandler`.

### Hardware mock backends exist only for cameras and 3D scanners
- **Location**: `mindtrace/hardware/`
- **Status**: `MockCamera` and `MockPhotoneo` exist. No mock backends for Stereo, PLCs, or Sensors.
- **Impact**: Unit tests for stereo cameras, PLCs, or sensors cannot use mock hardware; integration tests require real devices or Docker simulation.

---

## 4. API Correctness Checklist

Before writing code, confirm the API choices are right (workflow checklist is in `AGENTS.md`):

- [ ] I am using the correct Mindtrace-native component (see Decision Guide above).
- [ ] My change does not create an upward dependency (see Architecture boundary rule).
- [ ] I am subclassing `Mindtrace` (or `MindtraceABC`) for new classes, not `object` or raw `ABC`.
- [ ] I am using `self.logger` and `self.config`, not standalone logging or env reads.
- [ ] New services use `Service` + `TaskSchema` + `add_endpoint`. No raw FastAPI routers.
- [ ] New jobs use `Orchestrator` + `Consumer` + `JobSchema`. No Celery.
- [ ] New agents use `MindtraceAgent`. No direct OpenAI SDK calls.
- [ ] I checked Known Gaps above for any feature I am about to build.

> For testing commands, ruff, branching (`openclaw/<timestamp>-<short-summary>`), PR rules, and the full agent checklist — see `AGENTS.md`.

---

## 5. Quick Import Reference

```python
# Core
from mindtrace.core import Mindtrace, MindtraceABC, Config, TaskSchema
from mindtrace.core import EventBus, ObservableContext, ContextListener
from mindtrace.core import get_free_port, wait_for_service, Timeout, instantiate_target
from mindtrace.core import SystemMetricsCollector, compute_dir_hash, ifnone
from mindtrace.core.logging.logger import get_logger, track_operation

# Services
from mindtrace.services import Service, ConnectionManager, Gateway, ProxyConnectionManager

# Registry
from mindtrace.registry import Registry, Store
from mindtrace.registry import LocalRegistryBackend, S3RegistryBackend, GCPRegistryBackend
from mindtrace.registry.core.exceptions import RegistryObjectNotFound, RegistryVersionConflict

# Storage
from mindtrace.storage import GCSStorageHandler, S3StorageHandler, Status

# Database
from mindtrace.database import (
    UnifiedMindtraceODM, MongoMindtraceODM, RedisMindtraceODM, RegistryMindtraceODM,
    UnifiedMindtraceDocument, MindtraceDocument, MindtraceRedisDocument,
    BackendType, InitMode, DocumentNotFoundError, DuplicateInsertError,
)

# Jobs
from mindtrace.jobs import JobSchema, Orchestrator, Consumer, job_from_schema
from mindtrace.jobs import LocalClient, RedisClient, RabbitMQClient

# Cluster
from mindtrace.cluster import ClusterManager, Node, Worker
from mindtrace.cluster.workers.echo_worker import EchoWorker
from mindtrace.cluster.workers.run_script_worker import RunScriptWorker

# Agents
from mindtrace.agents import (
    MindtraceAgent, OpenAIChatModel, OpenAIProvider, OllamaProvider, GeminiProvider,
    Tool, RunContext, AgentCallbacks, InMemoryHistory,
    WrapperAgent, DistributedAgent, HandoffPart,
    JsonFileStore, MemoryToolset, LocalTaskQueue,
)
from mindtrace.agents.toolsets import FunctionToolset, MCPToolset, CompoundToolset, ToolFilter

# Hardware
from mindtrace.hardware import CameraManager, PLCManager
from mindtrace.hardware.cameras.core.camera import Camera
from mindtrace.hardware.stereo_cameras import StereoCamera
from mindtrace.hardware.scanners_3d import AsyncScanner3D
from mindtrace.hardware.sensors import AsyncSensor, MQTTSensorBackend
from mindtrace.hardware.services import CameraManagerService, PLCManagerService
from mindtrace.hardware import HomographyCalibrator, HomographyMeasurer

# Datalake
from mindtrace.datalake import DatalakeService, AsyncDatalake, Datalake, DataVault, AsyncDataVault

# Models
from mindtrace.models import (
    build_model, build_model_from_hf, list_backbones, register_backbone,
    Trainer, ModelCheckpoint, EarlyStopping, build_optimizer, build_scheduler,
    MLflowTracker, WandBTracker, TensorBoardTracker, CompositeTracker,
    EvaluationRunner, ModelCard, ModelStage, ModelService,
)
```

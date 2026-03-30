<p align="center">
  <img alt="Mindtrace" src="docs/assets/mindtrace-logo-horizontal.png" width="100%">
</p>

<p align="center">
  <a href="https://pypi.org/project/mindtrace/"><img alt="PyPI version" src="https://img.shields.io/pypi/v/mindtrace"></a>
  <a href="https://github.com/mindtrace/mindtrace/blob/main/LICENSE"><img alt="License" src="https://img.shields.io/pypi/l/mindtrace"></a>
  <a href="https://pepy.tech/projects/mindtrace"><img alt="Downloads" src="https://static.pepy.tech/badge/mindtrace"></a>
</p>

<h1 align="center">An Open Source Framework for AI Orchestration</h1>

Mindtrace is an open source Python framework for building, deploying, and operating end-to-end AI systems in production.

[Docs](https://mindtrace.github.io/mindtrace/) · [Samples](samples/) · [Contributing](CONTRIBUTING.md)

## Features

- **Modular infrastructure framework** with installable subpackages
- **Typed microservices** with auto-generated clients and MCP support
- **Artifact and object storage** through Registry and Storage layers
- **Database abstractions** for MongoDB, Redis, and Registry-backed persistence
- **Job queues and distributed execution** through Jobs and Cluster
- **LLM agents** with tools, memory, callbacks, and MCP toolsets
- **Hardware integration** for cameras, scanners, PLCs, and sensors
- **Composable architecture** where modules build naturally on top of one another

## Installation

```bash
pip install mindtrace
# or
uv add mindtrace
```

Or install only what you need:

```bash
pip install mindtrace-services   # Typed microservices
pip install mindtrace-registry   # Versioned artifact storage
pip install mindtrace-storage    # Object storage backends
pip install mindtrace-database   # ODM layer for MongoDB / Redis / Registry
pip install mindtrace-jobs       # Typed job queues
pip install mindtrace-cluster    # Distributed workers and routing
pip install mindtrace-agents     # LLM agents with tools and memory
pip install mindtrace-hardware   # Cameras, scanners, PLCs, sensors
```

## Quick Tour

The Mindtrace ecosystem is designed so that you can start small and compose modules as your system grows.

### Core

`mindtrace-core` gives you the shared building blocks used across the rest of the framework: configuration, logging, base classes, observables, and typed task schemas.

```python
from mindtrace.core import Mindtrace


class MyProcessor(Mindtrace):
    def run(self):
        self.logger.info(f"Temp dir: {self.config.MINDTRACE_DIR_PATHS.TEMP_DIR}")


with MyProcessor() as processor:
    processor.run()
```

### Services

`mindtrace-services` lets you define typed endpoints once and get a service plus a generated client.

```python
from pydantic import BaseModel

from mindtrace.core import TaskSchema
from mindtrace.services import Service


class EchoInput(BaseModel):
    message: str


class EchoOutput(BaseModel):
    echoed: str


echo_schema = TaskSchema(
    name="echo",
    input_schema=EchoInput,
    output_schema=EchoOutput,
)


class EchoService(Service):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.add_endpoint("echo", self.echo, schema=echo_schema)

    def echo(self, payload: EchoInput) -> EchoOutput:
        return EchoOutput(echoed=payload.message)


cm = EchoService.launch(host="localhost", port=8080, wait_for_launch=True)
print(cm.echo(message="Hello, world!").echoed)
cm.shutdown()
```

While the service is running, you can inspect the generated API docs at `http://localhost:8080/docs`.

### Registry

`mindtrace-registry` is the versioned artifact layer and supports local, S3-compatible, and GCS-backed registries.

```python
import numpy as np

from mindtrace.registry import Registry


embeddings = np.random.rand(100, 768).astype(np.float32)

registry = Registry()  # Defaults to the local registry at ~/.cache/mindtrace/registry
registry.save("data:embeddings", embeddings)
loaded = registry.load("data:embeddings")
print(loaded.shape)
```

You can also link the same `Registry` to a remote S3-compatible (AWS/Minio) or GCS backend.

```python
from mindtrace.registry import Registry, S3RegistryBackend


s3_backend = S3RegistryBackend(
    endpoint="localhost:9000",
    access_key="minioadmin",
    secret_key="minioadmin",
    bucket="mindtrace-registry",
    secure=False,
)
registry = Registry(s3_backend)

registry["data:embeddings"] = embeddings  # Registry also supports a convenient dict-like API
loaded = registry["data:embeddings"]
```

For multi-registry workflows, use `Store` to mount several registries behind one interface.

```python
from mindtrace.registry import Registry, Store


store = Store()
store.add_mount("local", Registry("~/.cache/mindtrace/temp/my_local_registry"))
store.add_mount("remote", Registry(s3_backend))
store.set_default_mount("local")

store["data:embeddings"] = embeddings  # Saves to the default mount
store["remote/data:embeddings"] = embeddings  # Qualify with mount name to target another mount

local_embeddings = store["local/data:embeddings"]
remote_embeddings = store["remote/data:embeddings"]
```

### Database

`mindtrace-database` provides a unified ODM layer over MongoDB, Redis, and Registry-backed storage.

```python
from pydantic import Field

from mindtrace.database import BackendType, UnifiedMindtraceDocument, UnifiedMindtraceODM


class User(UnifiedMindtraceDocument):
    name: str = Field(description="User name")
    email: str = Field(description="Email")

    class Meta:
        collection_name = "users"
        global_key_prefix = "myapp"
        indexed_fields = ["email"]
        unique_fields = ["email"]


db = UnifiedMindtraceODM(
    unified_model_cls=User,
    mongo_db_uri="mongodb://localhost:27017",
    mongo_db_name="myapp",
    redis_url="redis://localhost:6379",
    preferred_backend=BackendType.MONGO,
)

inserted = db.insert(User(name="Alice", email="alice@example.com"))
fetched = db.get(inserted.id)
print(fetched)
```

### Jobs

`mindtrace-jobs` gives you a unified job manager/orchestrator for typed jobs, with swappable local, Redis, and RabbitMQ backends.

```python
from pydantic import BaseModel

from mindtrace.jobs import Consumer, JobSchema, LocalClient, Orchestrator


class EchoInput(BaseModel):
    message: str


echo_schema = JobSchema(name="echo_job", input_schema=EchoInput)
orchestrator = Orchestrator(LocalClient())
orchestrator.register(echo_schema)


class EchoConsumer(Consumer):
    def run(self, job_dict: dict) -> dict:
        return {"echoed": job_dict["payload"]["message"]}


consumer = EchoConsumer()
consumer.connect_to_orchestrator(orchestrator, "echo_job")

orchestrator.publish("echo_job", EchoInput(message="Hello jobs"))
consumer.consume(num_messages=1)
```

### Cluster

`mindtrace-cluster` builds on `mindtrace-jobs` to add worker, compute-node, and resource management for queued jobs across services and machines.

```python
from mindtrace.cluster import ClusterManager, Node


cluster = ClusterManager.launch(host="localhost", port=8002, wait_for_launch=True)
node = Node.launch(host="localhost", port=8003, cluster_url=str(cluster.url), wait_for_launch=True)
print(cluster.status())
print(node.status())
```

### Hardware

`mindtrace-hardware` provides interfaces and service tooling for cameras, scanners, PLCs, and sensors.

```python
from mindtrace.hardware.cameras import Camera


camera = Camera(name="Basler:basler_camera_0")
image = camera.capture()
print(type(image))
camera.close()
```

### Agents

`mindtrace-agents` provides agents with tools, memory, callbacks, and MCP toolsets.

```python
from mindtrace.agents import MindtraceAgent, OpenAIChatModel, OpenAIProvider


provider = OpenAIProvider()
model = OpenAIChatModel("gpt-4o-mini", provider=provider)
agent = MindtraceAgent(model=model, name="assistant")

result = agent.run_sync("What is 2 + 2?")
print(result)
```

## Modules

| Module | Description |
|--------|-------------|
| [`core`](mindtrace/core) | Foundational abstractions for config, logging, observables, and typed schemas |
| [`services`](mindtrace/services) | Typed service framework with generated clients, launch helpers, and MCP support |
| [`registry`](mindtrace/registry) | Versioned artifact registry with local and remote backends |
| [`storage`](mindtrace/storage) | Lower-level object storage backends for GCS and S3-compatible services |
| [`database`](mindtrace/database) | Unified ODM layer for MongoDB, Redis, and Registry-backed persistence |
| [`jobs`](mindtrace/jobs) | Unified job manager/orchestrator for typed jobs across multiple queue backends |
| [`cluster`](mindtrace/cluster) | Worker, node, and cluster resource management on top of queued jobs |
| [`agents`](mindtrace/agents) | LLM agents with tools, memory, callbacks, streaming, and MCP integration |
| [`hardware`](mindtrace/hardware) | Hardware interfaces and service tooling for cameras, scanners, PLCs, and sensors |
| [`datalake`](mindtrace/datalake) | Dataset, model, label, and datum management |
| [`models`](mindtrace/models) | Model definitions, inference workflows, and related evaluation utilities |
| [`automation`](mindtrace/automation) | Pipeline orchestration and workflow integrations |
| [`ui`](mindtrace/ui) | UI components and visualization tools |
| [`apps`](mindtrace/apps) | End-user applications and demos |

## Module Dependencies

<details>
<summary>Show module dependency diagram</summary>

```mermaid
%%{init: {'flowchart': {'curve': 'stepAfter'}}}%%
flowchart TB
    subgraph L1[Foundation]
        core[core]
    end

    subgraph L2[Core infrastructure]
        services[services]
        registry[registry]
        storage[storage]
        database[database]
        jobs[jobs]
    end

    subgraph L3[Higher-level systems]
        cluster[cluster]
        agents[agents]
        hardware[hardware]
        datalake[datalake]
        models[models]
    end

    subgraph L4[Orchestration and apps]
        automation[automation]
        ui[ui]
        apps[apps]
    end

    core --> services
    core --> registry
    core --> storage
    core --> database
    core --> jobs

    storage --> registry
    registry --> database

    services --> cluster
    jobs --> cluster
    registry --> cluster
    database --> cluster

    core --> agents
    services --> agents
    database --> agents

    core --> hardware
    services --> hardware
    database --> hardware
    registry --> hardware

    core --> datalake
    registry --> datalake
    database --> datalake
    services --> datalake

    core --> models
    registry --> models
    database --> models
    services --> models

    cluster --> automation
    services --> automation
    agents --> automation
    datalake --> automation
    models --> automation

    core --> ui
    services --> ui

    automation --> apps
    ui --> apps
    services --> apps
    agents --> apps
```

</details>

## Choose the Right Module

If you are not sure where to start:

- **Need config, logging, base utilities, or typed schemas?** → [`core`](mindtrace/core)
- **Need a deployable API or MCP-capable service?** → [`services`](mindtrace/services)
- **Need versioned artifact storage?** → [`registry`](mindtrace/registry)
- **Need a document/database abstraction?** → [`database`](mindtrace/database)
- **Need queue-backed background jobs?** → [`jobs`](mindtrace/jobs)
- **Need distributed workers across machines?** → [`cluster`](mindtrace/cluster)
- **Need LLM agents with tools and memory?** → [`agents`](mindtrace/agents)
- **Need industrial hardware/device integration?** → [`hardware`](mindtrace/hardware)
- **Need data/model/label management?** → [`datalake`](mindtrace/datalake)

Mindtrace is intentionally layered so higher-level modules build on lower-level ones rather than duplicating shared concerns. You do not need to adopt every module at once; most projects start with just one or two and grow from there.

## Documentation

- [Full Documentation](https://mindtrace.github.io/mindtrace/)
- [Samples](samples/)
- [Contributing](CONTRIBUTING.md)

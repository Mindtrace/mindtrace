# Mindtrace Distributed Agents — Low-Level Design

**Version:** 1.2  
**Date:** 2026-04-11  
**Status:** Draft — revised per security & architecture review

---

## Table of Contents

1. [Overview](#1-overview)
2. [Package Structure](#2-package-structure)
3. [WebSocket Gateway Design](#3-websocket-gateway-design)
4. [Core Class Signatures](#4-core-class-signatures)
5. [Data Flow Diagrams](#5-data-flow-diagrams)
6. [Memory & Context Architecture](#6-memory--context-architecture)
7. [Authentication & Authorization Model](#7-authentication--authorization-model)
8. [Failure, Retry & Dead-Letter Semantics](#8-failure-retry--dead-letter-semantics)
9. [Circuit-Breaker & Backpressure](#9-circuit-breaker--backpressure)
10. [Observability Design](#10-observability-design)
11. [Agent & Dependency Class Allowlist Registry](#11-agent--dependency-class-allowlist-registry)
12. [Plugin System](#12-plugin-system)
13. [Implementation Tasks](#13-implementation-tasks)
14. [Design Decisions & Trade-offs](#14-design-decisions--trade-offs)
15. [Memory Management API](#15-memory-management-api)

---

## 1. Overview

This document describes the design for extending the **mindtrace** library to support fully distributed AI agent execution across separate machines. The design extends only two existing packages — `mindtrace-agents` and `mindtrace-cluster` — using optional extras, introducing no new packages. The supported topology is:

```
User (Machine A)  →  MindtraceAgentGateway (Machine B)  →  MindtraceAgentWorker (Machine C+)
```

### Goals

- Run agents on remote machines with no changes to existing `MindtraceAgent` code
- Stream `NativeEvent` tokens from a remote agent to a client in real-time over WebSocket
- Provide short-term (Redis) and long-term (MongoDB) memory implementations for `AbstractMemoryStore`
- Propagate `RunContext`, session ID, and trace ID across process and network boundaries
- Emit observable spans from every agent run, aggregated by a central collector
- Allow third-party skills and model providers to be registered via Python entry-points

### What Is NOT Changed

- `AbstractMindtraceAgent`, `MindtraceAgent`, `RunContext`, `AgentTask`, `AbstractTaskQueue` — all existing interfaces are preserved
- `LocalTaskQueue` — continues to work as-is for local/single-process use
- `InMemoryHistory` — continues to work as-is
- `Service`, `Gateway`, `ClusterManager`, `Node`, `Worker` — extended, not modified
- `mindtrace-cluster` — unchanged; pulled in only when `mindtrace-agents[distributed-cluster]` is installed

### Package Strategy

Rather than introducing new packages, distributed agent components are:
- Added as **submodules** inside `mindtrace-agents` (queue impls, memory, history, context, observability, plugins, distributed runtime)
- Guarded by **optional extras** so a basic `pip install mindtrace-agents` stays lean (`openai + pydantic + mindtrace-core` only)
- The `[distributed-cluster]` extra pulls in `mindtrace-cluster` as a dependency, making `Worker`, `Node`, and `Gateway` available for subclassing in `mindtrace/agents/distributed/`

This follows the pattern already established in `mindtrace-agents/pyproject.toml` which already defines `mcp`, `distributed-rabbitmq`, `memory-redis`, and `memory-vector` as optional extras.

---

## 2. Package Structure

No new packages are introduced. All changes land inside the two existing packages via new submodules and optional extras.

### `mindtrace-agents` — extended in-place

```
mindtrace/agents/
├── execution/
│   ├── _queue.py              (AbstractTaskQueue — existing)
│   ├── local.py               (LocalTaskQueue — existing)
│   ├── rabbitmq.py            (RabbitMQAgentTaskQueue — NEW)
│   └── redis.py               (RedisAgentTaskQueue — NEW)
├── history/
│   ├── _strategy.py           (AbstractHistoryStrategy — existing)
│   ├── in_memory.py           (InMemoryHistory — existing)
│   └── redis.py               (RedisHistoryStrategy — NEW)
├── memory/
│   ├── _store.py              (AbstractMemoryStore — existing)
│   ├── redis.py               (RedisMemoryStore — NEW)
│   └── mongo.py               (MongoMemoryStore — NEW)
├── context/
│   └── propagation.py         (AgentRunContext, AgentTaskEnvelope — NEW)
├── observability/
│   ├── span.py                (AgentSpan, AgentObservabilityMixin — NEW)
│   └── callbacks.py           (_ObservabilityCallbacks — NEW)
├── plugins/                   (NEW — replaces proposed mindtrace-plugins package)
│   ├── registry.py            (MindtracePluginRegistry)
│   ├── skill.py               (AbstractSkill)
│   └── providers.py           (AbstractModelProviderPlugin)
└── distributed/               (NEW — replaces proposed mindtrace-distributed package)
    │                          (only importable when [distributed-cluster] extra installed)
    ├── worker.py              (MindtraceAgentWorker)
    ├── node.py                (MindtraceAgentNode)
    ├── gateway.py             (MindtraceAgentGateway)
    ├── registry.py            (MindtraceAgentRegistry)
    ├── collector.py           (AgentObservabilityCollector)
    └── types.py               (Pydantic wire protocol models)
```

### Updated `mindtrace-agents/pyproject.toml`

```toml
[project.optional-dependencies]
mcp                  = ["fastmcp>=2.13.0"]
distributed-rabbitmq = ["aio-pika>=9.0"]        # existing
distributed-cluster  = ["mindtrace-cluster>=0.10.0"]  # NEW — unlocks agents/distributed/
memory-redis         = ["redis>=5.0"]            # existing
memory-mongo         = ["motor>=3.0"]            # NEW — unlocks MongoMemoryStore
memory-vector        = ["chromadb>=0.4"]         # existing
distributed          = [                         # NEW — convenience bundle
    "mindtrace-agents[distributed-rabbitmq]",
    "mindtrace-agents[distributed-cluster]",
    "mindtrace-agents[memory-redis]",
    "mindtrace-agents[memory-mongo]",
]
```

### `mindtrace-cluster` — unchanged

No modifications. It is pulled in as a dependency only when `mindtrace-agents[distributed-cluster]` is installed, making `Worker`, `Node`, and `Gateway` available for subclassing inside `mindtrace/agents/distributed/`.

### Dependency Graph

```
mindtrace-core
    └── mindtrace-agents   (lean: openai + pydantic + core)
            ├── [memory-redis]          → redis
            ├── [memory-mongo]          → motor
            ├── [distributed-rabbitmq]  → aio-pika
            └── [distributed-cluster]   → mindtrace-cluster
                                              (jobs, registry, database, services, docker)
```

### Install Paths

```bash
# Local development — stays lean
pip install mindtrace-agents

# Add persistent Redis memory and history
pip install "mindtrace-agents[memory-redis]"

# Full distributed deployment (all extras)
pip install "mindtrace-agents[distributed]"
```

### Module Responsibilities

| Submodule | Extra required | Responsibility |
|---|---|---|
| `agents/execution/rabbitmq.py` | `distributed-rabbitmq` | RabbitMQ-backed task queue |
| `agents/execution/redis.py` | `memory-redis` | Redis-backed task queue |
| `agents/history/redis.py` | `memory-redis` | Persistent session history |
| `agents/memory/redis.py` | `memory-redis` | Short-term TTL memory store |
| `agents/memory/mongo.py` | `memory-mongo` | Long-term vector memory store |
| `agents/context/` | none | Cross-process context propagation models |
| `agents/observability/` | none | Span model, observability mixin |
| `agents/plugins/` | none | Skill/provider plugin registry |
| `agents/distributed/` | `distributed-cluster` | Gateway, worker, node, registry, collector |

---

## 3. WebSocket Gateway Design

### Why WebSocket

| Option | Verdict | Reason |
|---|---|---|
| **WebSocket** | **Chosen (streaming)** | Bidirectional, persistent, low overhead; `NativeEvent` stream maps naturally to WS frames; supports multi-turn sessions |
| HTTP REST | Chosen (one-shot fallback) | Simple invocations that don't need streaming |
| SSE | Rejected | Server-push only; client cannot send session messages |
| gRPC | Rejected | Heavy dependency; adds operational complexity; WS composable with existing FastAPI |

### Connection Lifecycle

```
Client (Machine A)                          MindtraceAgentGateway (Machine B)
  │
  │── WS connect: GET /ws/agents ─────────▶ authenticate (token in header/query)
  │◀─ {"type": "connected",                 assign session_id if not provided
  │    "session_id": "...",         ────────
  │    "gateway_id": "..."}
  │
  │── AgentInvokeRequest ─────────────────▶ validate request
  │   (agent_name, input, session_id,        create AgentTaskEnvelope
  │    deps, stream=true)                    publish to RabbitMQ queue
  │◀─ {"type": "ack", "task_id": "..."}  ──
  │
  │                    [MindtraceAgentWorker picks up task on Machine C]
  │                    [executes agent.run_stream_events()]
  │                    [publishes NativeEvents to Redis Pub/Sub: channel task:{task_id}]
  │
  │◀─ AgentStreamEvent (part_start) ────── gateway subscribes to Redis channel
  │◀─ AgentStreamEvent (part_delta) ────── relays each event as a WS frame
  │◀─ AgentStreamEvent (part_delta)
  │◀─ AgentStreamEvent (tool_result)
  │◀─ AgentStreamEvent (part_end)
  │◀─ AgentInvokeResponse (final) ──────── includes output, span_id, usage
  │
  │── WS disconnect ──────────────────────▶ cleanup subscription
```

### Wire Protocol — Pydantic Models

```python
# ── Client → Gateway ──────────────────────────────────────────────────────

class AgentInvokeRequest(BaseModel):
    agent_name: str
    input: str
    session_id: str | None = None        # omit to start a new session
    deps: dict[str, Any] = {}
    stream: bool = True                  # False → REST-style, wait for full result
    metadata: dict[str, Any] = {}

# ── Gateway → Client ──────────────────────────────────────────────────────

class AgentSessionMessage(BaseModel):
    """Sent immediately on WebSocket connect."""
    type: Literal["connected"] = "connected"
    session_id: str
    gateway_id: str

class AgentAckMessage(BaseModel):
    """Sent after AgentInvokeRequest is enqueued."""
    type: Literal["ack"] = "ack"
    task_id: str
    trace_id: str

class AgentStreamEvent(BaseModel):
    """One-to-one wrapper around NativeEvent, sent per streaming frame."""
    type: Literal["stream_event"] = "stream_event"
    task_id: str
    trace_id: str
    event_kind: Literal[
        "part_start", "part_delta", "part_end",
        "tool_result", "result"
    ]
    payload: dict[str, Any]              # serialized NativeEvent fields

class AgentInvokeResponse(BaseModel):
    """Final message when agent run completes."""
    type: Literal["response"] = "response"
    task_id: str
    trace_id: str
    span_id: str
    session_id: str
    output: Any
    usage: TokenUsage | None = None

class AgentErrorMessage(BaseModel):
    type: Literal["error"] = "error"
    task_id: str | None = None
    trace_id: str
    code: str                            # "auth_failed" | "agent_not_found" | "timeout" | "execution_error"
    message: str

class TokenUsage(BaseModel):
    input_tokens: int
    output_tokens: int
    model_name: str
```

### REST Fallback Endpoints

The gateway exposes REST endpoints alongside the WebSocket interface. The full API surface is grouped by domain below. All endpoints except `GET /health` require authentication.

#### Agent Invocation

```
POST   /agents/{name}/invoke             → AgentInvokeResponse        (blocks; no streaming)
GET    /agents/{name}/tasks/{task_id}    → TaskStatusResponse
GET    /agents/                          → list[AgentInfo]
GET    /health                           → HealthStatus                (unauthenticated)
```

#### Session & Conversation History

```
GET    /sessions/{session_id}/history    → list[ModelMessage]          (scope: tasks:read)
DELETE /sessions/{session_id}/history    → 204                         (scope: tasks:cancel)
GET    /sessions?user_id={user_id}       → list[SessionInfo]           (scope: tasks:read)
```

#### Memory — Session scope  (Redis; volatile, TTL-scoped)

```
GET    /memory/sessions/{session_id}                    → list[MemoryEntry]   (scope: tasks:read)
POST   /memory/sessions/{session_id}/entries            → MemoryEntry         (scope: tasks:submit)
GET    /memory/sessions/{session_id}/entries/{key}      → MemoryEntry         (scope: tasks:read)
DELETE /memory/sessions/{session_id}/entries/{key}      → 204                 (scope: tasks:cancel)
GET    /memory/sessions/{session_id}/search?q=&top_k=   → list[MemoryEntry]   (scope: tasks:read)
```

#### Memory — User scope  (MongoDB; persistent, cross-session)

```
GET    /memory/users/{user_id}                          → list[MemoryEntry]   (scope: memory:read; own user or admin)
POST   /memory/users/{user_id}/entries                  → MemoryEntry         (scope: memory:write; own user or admin)
GET    /memory/users/{user_id}/entries/{key}            → MemoryEntry         (scope: memory:read)
PUT    /memory/users/{user_id}/entries/{key}            → MemoryEntry         (scope: memory:write)
DELETE /memory/users/{user_id}/entries/{key}            → 204                 (scope: memory:write)
GET    /memory/users/{user_id}/search?q=&top_k=         → list[MemoryEntry]   (scope: memory:read)
```

#### Memory — Project scope  (MongoDB; persistent, project-scoped)

```
GET    /memory/projects/{project_id}                    → list[MemoryEntry]   (scope: project:member)
POST   /memory/projects/{project_id}/entries            → MemoryEntry         (scope: project:member)
GET    /memory/projects/{project_id}/entries/{key}      → MemoryEntry         (scope: project:member)
PUT    /memory/projects/{project_id}/entries/{key}      → MemoryEntry         (scope: project:member)
DELETE /memory/projects/{project_id}/entries/{key}      → 204                 (scope: project:member)
GET    /memory/projects/{project_id}/search?q=&top_k=   → list[MemoryEntry]   (scope: project:member)
```

#### Memory — Organisation scope  (MongoDB; persistent, org-wide)

```
GET    /memory/orgs/{org_id}                            → list[MemoryEntry]   (scope: org:member)
POST   /memory/orgs/{org_id}/entries                    → MemoryEntry         (scope: org:member)
GET    /memory/orgs/{org_id}/entries/{key}              → MemoryEntry         (scope: org:member)
PUT    /memory/orgs/{org_id}/entries/{key}              → MemoryEntry         (scope: org:admin; write is admin-only)
DELETE /memory/orgs/{org_id}/entries/{key}              → 204                 (scope: org:admin)
GET    /memory/orgs/{org_id}/search?q=&top_k=           → list[MemoryEntry]   (scope: org:member)
```

#### Observability  (on `AgentObservabilityCollector`)

```
POST   /spans                                           → 201                 (scope: spans:ingest)
POST   /spans/query                                     → list[AgentSpan]     (scope: metrics:read)
GET    /metrics/{agent_name}                            → AgentMetrics        (scope: metrics:read)
GET    /health                                          → HealthStatus        (unauthenticated)
```

#### Admin / Registry

```
POST   /agents/register                                 → AgentDefinition     (scope: agents:manage)
DELETE /agents/{name}                                   → 204                 (scope: agents:manage)
GET    /workers                                         → list[WorkerInfo]    (scope: agents:list)
POST   /allowlist                                       → AllowlistEntry      (scope: allowlist:manage)
DELETE /allowlist/{path}                                → 204                 (scope: allowlist:manage)
GET    /allowlist                                       → list[AllowlistEntry](scope: allowlist:manage)
GET    /dlq                                             → list[DLQRecord]     (scope: dlq:manage)
POST   /dlq/requeue/{task_id}                           → 202                 (scope: dlq:manage)
POST   /dlq/requeue-all                                 → RequeueAllResponse  (scope: dlq:manage)
POST   /dlq/purge                                       → 204                 (scope: dlq:manage)
```

---

## 4. Core Class Signatures

### 4.1 `mindtrace/agents/distributed/` (requires `[distributed-cluster]` extra)

#### `MindtraceAgentGateway`

```python
from mindtrace.services import Gateway
from mindtrace.distributed.registry import MindtraceAgentRegistry
from mindtrace.agents.execution import AbstractTaskQueue

class MindtraceAgentGateway(Gateway):
    """
    WebSocket + REST entry point for distributed agent execution.
    Extends the existing Gateway with:
      - WebSocket endpoint for streaming agent invocation
      - REST fallback for non-streaming invocation
      - Redis Pub/Sub relay of NativeEvents to connected WebSocket clients
    """

    def __init__(
        self,
        registry: MindtraceAgentRegistry,
        task_queue: AbstractTaskQueue,           # typically RabbitMQAgentTaskQueue
        collector_url: str | None = None,        # AgentObservabilityCollector URL
        auth_secret: str | None = None,          # shared secret for WS auth
        **kwargs: Any,
    ) -> None: ...

    # WebSocket endpoint — registered at /ws/agents
    async def websocket_endpoint(self, websocket: WebSocket) -> None: ...

    # REST endpoints — registered via add_endpoint()
    async def invoke_agent(
        self,
        name: str,
        request: AgentInvokeRequest,
    ) -> AgentInvokeResponse: ...

    async def get_task_status(self, task_id: str) -> TaskStatusResponse: ...
    async def list_agents(self) -> list[AgentInfo]: ...

    # Internal helpers
    async def _relay_stream(self, task_id: str, websocket: WebSocket) -> None:
        """Subscribe to Redis Pub/Sub channel task:{task_id}, relay frames over WS."""
        ...

    async def _authenticate(self, websocket: WebSocket) -> str:
        """Validate bearer token. Returns user_id."""
        ...

    def _build_context(
        self,
        request: AgentInvokeRequest,
        user_id: str,
    ) -> AgentRunContext: ...
```

#### `MindtraceAgentWorker`

```python
from mindtrace.cluster import Worker
from mindtrace.distributed.registry import MindtraceAgentRegistry
from mindtrace.plugins import MindtracePluginRegistry
from mindtrace.agents.observability import AgentObservabilityMixin

class MindtraceAgentWorker(Worker):
    """
    Worker subclass that loads AbstractMindtraceAgent objects from the registry
    and executes them. Publishes NativeEvents to Redis Pub/Sub for gateway relay.
    Extends Worker._run() with agent-specific lifecycle.
    """

    def __init__(
        self,
        agent_registry: MindtraceAgentRegistry,
        plugin_registry: MindtracePluginRegistry | None = None,
        collector_url: str | None = None,
        redis_pubsub_url: str | None = None,     # for NativeEvent relay
        **kwargs: Any,
    ) -> None: ...

    def _run(self, job_dict: dict) -> dict:
        """
        Called by Worker.run() in a thread. Bridges sync→async via
        asyncio.get_event_loop().run_until_complete(_run_agent()).
        Note: if Worker already runs _run() inside an event loop, replace
        with direct await.
        """
        ...

    async def _run_agent(self, envelope: AgentTaskEnvelope) -> Any:
        """Load agent, reconstruct context, execute, stream events."""
        ...

    def _load_agent(self, agent_name: str) -> AbstractMindtraceAgent:
        """Fetch AgentDefinition from registry; instantiate with plugins."""
        ...

    async def _publish_event(self, task_id: str, event: NativeEvent) -> None:
        """Publish serialized NativeEvent to Redis channel task:{task_id}."""
        ...

    async def _publish_result(self, task_id: str, result: Any) -> None:
        """Write final result to Redis key result:{task_id} with TTL."""
        ...
```

#### `MindtraceAgentNode`

```python
from mindtrace.cluster import Node

class MindtraceAgentNode(Node):
    """
    Node subclass that launches MindtraceAgentWorker subprocesses.
    Registers workers with MindtraceAgentRegistry on launch.
    """

    def __init__(
        self,
        agent_registry_url: str,
        worker_class: type[MindtraceAgentWorker] = MindtraceAgentWorker,
        plugin_registry: MindtracePluginRegistry | None = None,
        **kwargs: Any,
    ) -> None: ...

    async def launch_worker(self, payload: LaunchWorkerInput) -> LaunchWorkerOutput:
        """Extends Node.launch_worker() to register launched worker in agent registry."""
        ...
```

#### `MindtraceAgentRegistry`

```python
from mindtrace.core import Mindtrace

class AgentDefinition(BaseModel):
    """
    Serializable agent specification stored in the registry.

    SECURITY: agent_class is validated against MindtraceAllowlistRegistry at
    registration time (register_agent() rejects unknown paths) and again at
    load time in MindtraceAgentWorker._load_agent(). Only paths explicitly
    registered in the allowlist may be instantiated. See Section 11.
    """
    name: str
    description: str | None = None
    agent_class: str                         # allowlisted dotted path, e.g. "myapp.agents:MyAgent"
    init_kwargs: dict[str, Any] = {}         # passed to agent.__init__()
    required_skills: list[str] = []          # skill names that must be available
    required_provider: str | None = None     # model provider name
    org_id: str | None = None               # scope to a specific organisation; None = available to all orgs
    project_id: str | None = None           # scope to a specific project; None = not project-scoped

class WorkerInfo(BaseModel):
    worker_id: str
    node_id: str
    url: str                                 # worker service URL
    agent_names: list[str]
    status: WorkerStatusEnum
    last_heartbeat: datetime

class MindtraceAgentRegistry(Mindtrace):
    """
    Redis-backed registry for agent definitions and live worker locations.
    Workers register on startup and send heartbeats; stale entries are
    evicted after 3 missed heartbeats.
    """

    def __init__(
        self,
        redis_url: str,
        heartbeat_ttl: int = 30,             # seconds; worker evicted if no heartbeat
        **kwargs: Any,
    ) -> None: ...

    async def register_agent(self, definition: AgentDefinition) -> None: ...
    async def get_agent_definition(self, agent_name: str) -> AgentDefinition | None: ...
    async def list_agents(self) -> list[AgentDefinition]: ...

    async def register_worker(
        self,
        worker_id: str,
        agent_names: list[str],
        url: str,
        node_id: str,
    ) -> None: ...

    async def heartbeat(self, worker_id: str) -> None:
        """Refresh TTL on worker key. Called by worker on a background thread."""
        ...

    async def find_workers(self, agent_name: str) -> list[WorkerInfo]:
        """Return all live workers capable of running agent_name."""
        ...

    async def deregister_worker(self, worker_id: str) -> None: ...
```

#### `AgentObservabilityCollector`

```python
from mindtrace.services import Service
from mindtrace.agents.observability.span import AgentSpan

class SpanQuery(BaseModel):
    agent_name: str | None = None
    session_id: str | None = None
    trace_id: str | None = None
    from_time: datetime | None = None
    to_time: datetime | None = None
    status: Literal["ok", "error"] | None = None
    limit: int = 100

class AgentMetrics(BaseModel):
    agent_name: str
    total_runs: int
    error_rate: float
    latency_p50_ms: float
    latency_p95_ms: float
    latency_p99_ms: float
    total_input_tokens: int
    total_output_tokens: int
    tool_call_counts: dict[str, int]

class AgentObservabilityCollector(Service):
    """
    Centralized span ingestion and metrics service.
    Workers POST spans here; this service exports to OTLP and
    exposes a query API.
    Registered endpoint: POST /spans, GET /metrics/{agent_name}, POST /spans/query
    """

    def __init__(
        self,
        otlp_endpoint: str | None = None,    # e.g. "http://jaeger:4318"
        mongo_url: str | None = None,        # for span persistence
        **kwargs: Any,
    ) -> None: ...

    async def ingest_span(self, span: AgentSpan) -> None: ...
    async def query_spans(self, query: SpanQuery) -> list[AgentSpan]: ...
    async def agent_metrics(self, agent_name: str) -> AgentMetrics: ...
    async def _export_otlp(self, span: AgentSpan) -> None: ...
```

---

### 4.2 `mindtrace/agents/` Core Extensions (no extra required)

#### `AgentTaskEnvelope`

```python
from pydantic import BaseModel, Field
from uuid import uuid4

class TaskProvenance(BaseModel):
    """Records the origin and submitter of a task for audit and routing."""
    submitter_id: str                        # user_id of the authenticated submitter
    submitter_role: str                      # role at submission time (e.g. "user", "service")
    origin_gateway_id: str                   # gateway instance that created the envelope
    origin_ip: str | None = None             # client IP, if available and permitted by policy
    client_request_id: str | None = None     # optional idempotency key from the client

class AgentTaskEnvelope(BaseModel):
    """
    Wire format for messages published to RabbitMQ or Redis queues.
    Contains everything the worker needs to reconstruct execution context.

    TTL / expiry semantics:
      - task_ttl_seconds: the worker MUST not start execution after this deadline;
        it should NACK the message and route to the DLQ instead.
      - result_ttl_seconds: how long the result key lives in Redis after completion.
        Callers that do not retrieve results within this window will receive a
        ResultExpiredError rather than a stale or missing result.
    """
    task_id: str = Field(default_factory=lambda: str(uuid4()))
    agent_name: str
    input: str
    session_id: str | None = None
    run_context: AgentRunContext
    provenance: TaskProvenance               # submitter identity and origin (see above)
    submitted_at: datetime = Field(default_factory=datetime.utcnow)
    task_ttl_seconds: int = 300              # worker must begin execution before this expires
    result_ttl_seconds: int = 3600           # Redis result key TTL after task completes
    result_channel: str                      # Redis Pub/Sub channel: "task:{task_id}"
    result_key: str                          # Redis result key: "result:{task_id}"
    retry_count: int = 0                     # incremented on each requeue; capped at max_retries
    metadata: dict[str, Any] = {}
```

#### `AgentRunContext`

```python
from pydantic import BaseModel

class AgentRunContext(BaseModel):
    """
    Serializable version of RunContext for cross-process and cross-network propagation.
    Carries W3C TraceContext-compatible identifiers and serialized deps.
    """
    trace_id: str                            # W3C traceparent trace-id (32 hex chars)
    span_id: str                             # W3C traceparent parent-id (16 hex chars)
    session_id: str
    user_id: str
    org_id: str | None = None               # routes org-scoped memory lookups; None if not in an org context
    project_id: str | None = None           # routes project-scoped memory lookups; None if not in a project context
    run_id: str | None = None
    baggage: dict[str, str] = {}             # W3C Baggage key=val pairs
    deps_json: str = "{}"                    # JSON-serialized deps (Pydantic model)
    deps_type_path: str = "builtins.NoneType"
    # ^^^ SECURITY: deps_type_path is validated against MindtraceAllowlistRegistry
    # before any import is attempted. See Section 11. Arbitrary paths from untrusted
    # input are rejected with AllowlistViolationError.
    step: int = 0
    retry: int = 0

    def to_run_context(self) -> RunContext:
        """
        Deserialize deps_json using deps_type_path; return RunContext.

        Raises:
            AllowlistViolationError: if deps_type_path is not in the allowlist.
            ImportError: if the allowed path cannot be imported.
            ValidationError: if deps_json does not conform to the deps type schema.
        """
        ...

    @classmethod
    def from_run_context(
        cls,
        ctx: RunContext,
        trace_id: str,
        span_id: str,
        session_id: str,
        user_id: str,
        baggage: dict[str, str] | None = None,
    ) -> "AgentRunContext": ...

    def to_headers(self) -> dict[str, str]:
        """Serialize as HTTP headers (W3C traceparent + X-Mindtrace-Baggage)."""
        ...

    @classmethod
    def from_headers(cls, headers: dict[str, str]) -> "AgentRunContext": ...
```

#### `RabbitMQAgentTaskQueue`

```python
from mindtrace.agents.execution._queue import AbstractTaskQueue, AgentTask, TaskStatus

class RabbitMQAgentTaskQueue(AbstractTaskQueue):
    """
    Publishes AgentTaskEnvelopes to a RabbitMQ exchange.
    Results and streaming events are read from Redis.
    DLQ: failed tasks routed to mindtrace.agent.tasks.dlq exchange.
    """

    def __init__(
        self,
        rabbitmq_url: str,
        redis_url: str,
        queue_name: str = "mindtrace.agent.tasks",
        dlq_name: str = "mindtrace.agent.tasks.dlq",
        result_ttl: int = 3600,
        max_retries: int = 3,
    ) -> None: ...

    async def submit(self, task: AgentTask) -> str:
        """Serialize task to AgentTaskEnvelope, publish to RabbitMQ. Returns task_id."""
        ...

    async def get_result(self, task_id: str, timeout: int = 300) -> Any:
        """Poll Redis result key with exponential backoff. Raises TimeoutError."""
        ...

    async def cancel(self, task_id: str) -> None:
        """Write cancellation flag to Redis; worker checks flag before executing."""
        ...

    async def status(self, task_id: str) -> TaskStatus:
        """Read status key from Redis."""
        ...

    async def requeue_from_dlq(self, task_id: str) -> None:
        """Move message from DLQ back to main queue for retry."""
        ...
```

#### `RedisAgentTaskQueue`

```python
class RedisAgentTaskQueue(AbstractTaskQueue):
    """
    Lightweight Redis list-based queue for smaller deployments.
    Uses LPUSH for submit, BRPOP for worker consumption.
    """

    def __init__(
        self,
        redis_url: str,
        queue_name: str = "mindtrace:agent:tasks",
        result_ttl: int = 3600,
    ) -> None: ...

    async def submit(self, task: AgentTask) -> str: ...
    async def get_result(self, task_id: str, timeout: int = 300) -> Any: ...
    async def cancel(self, task_id: str) -> None: ...
    async def status(self, task_id: str) -> TaskStatus: ...
```

#### `RedisHistoryStrategy`

```python
from mindtrace.agents.history._strategy import AbstractHistoryStrategy

class RedisHistoryStrategy(AbstractHistoryStrategy):
    """
    Redis-backed conversation history. Messages serialized as JSON lists.
    Isolated per session_id. Configurable TTL refreshed on every save().
    """

    def __init__(
        self,
        redis_url: str,
        ttl: int = 86400,                    # 24h default
        key_prefix: str = "mindtrace:history",
        **kwargs: Any,
    ) -> None: ...

    async def load(self, session_id: str) -> list[ModelMessage]: ...
    async def save(self, session_id: str, messages: list[ModelMessage]) -> None: ...
    async def clear(self, session_id: str) -> None: ...

    def _key(self, session_id: str) -> str:
        return f"{self.key_prefix}:{session_id}"
```

#### `RedisMemoryStore`

```python
from mindtrace.agents.memory._store import AbstractMemoryStore, MemoryEntry

class RedisMemoryStore(AbstractMemoryStore):
    """
    Short-term TTL-scoped memory backed by Redis hashes.
    Keys are namespaced: {namespace}:{key}
    search() performs prefix scan (no vector search).
    """

    def __init__(
        self,
        redis_url: str,
        namespace: str,                      # e.g. "session:abc123" or "agent:my_agent"
        default_ttl: int = 3600,
        **kwargs: Any,
    ) -> None: ...

    async def save(
        self,
        key: str,
        value: str,
        metadata: dict | None = None,
        ttl: int | None = None,              # overrides default_ttl
    ) -> None: ...

    async def get(self, key: str) -> MemoryEntry | None: ...
    async def search(self, query: str, top_k: int = 5) -> list[MemoryEntry]: ...
    async def delete(self, key: str) -> None: ...
    async def list_keys(self) -> list[str]: ...
```

#### `MongoMemoryStore`

```python
from typing import Protocol

class EmbeddingProvider(Protocol):
    """Protocol for pluggable embedding backends."""
    async def embed(self, text: str) -> list[float]: ...

class MongoMemoryStore(AbstractMemoryStore):
    """
    Long-term memory with optional vector search backed by MongoDB.
    Requires Atlas Search or mongod with vector index for vector search.
    Falls back to $text search if no embedding_provider is configured.
    Namespaced: documents tagged with namespace field for isolation.
    """

    def __init__(
        self,
        mongo_url: str,
        database: str,
        collection: str,
        namespace: str,                      # e.g. "agent:my_agent:user:user123"
        embedding_provider: EmbeddingProvider | None = None,
        vector_index_name: str = "vector_index",
        **kwargs: Any,
    ) -> None: ...

    async def save(self, key: str, value: str, metadata: dict | None = None) -> None: ...
    async def get(self, key: str) -> MemoryEntry | None: ...

    async def search(self, query: str, top_k: int = 5) -> list[MemoryEntry]:
        """Vector search if embedding_provider set, else $text search."""
        ...

    async def delete(self, key: str) -> None: ...
    async def list_keys(self) -> list[str]: ...
```

#### `AgentObservabilityMixin`

```python
class AgentObservabilityMixin:
    """
    MRO mixin that wraps run() and run_stream_events() with span emission.
    Used via multiple inheritance:
        class MindtraceAgentWorker(AgentObservabilityMixin, Worker): ...

    Does NOT modify AbstractMindtraceAgent or MindtraceAgent.
    Preserves isinstance(agent, AbstractMindtraceAgent) checks.
    """

    _collector_url: str | None = None
    _worker_id: str = "unknown"

    async def run(
        self,
        input_data: Any,
        *,
        deps: Any = None,
        **kwargs: Any,
    ) -> Any:
        span = AgentSpan.start(
            agent_name=getattr(self, "name", "unknown"),
            worker_id=self._worker_id,
            run_context=kwargs.get("_run_context"),
        )
        try:
            result = await super().run(input_data, deps=deps, **kwargs)
            span.finish(status="ok", output=result)
            return result
        except Exception as e:
            span.finish(status="error", error=str(e))
            raise
        finally:
            await self._emit_span(span)

    async def run_stream_events(
        self,
        input_data: Any,
        **kwargs: Any,
    ) -> AsyncIterator[NativeEvent]:
        span = AgentSpan.start(agent_name=getattr(self, "name", "unknown"), ...)
        try:
            async for event in super().run_stream_events(input_data, **kwargs):
                span.record_event(event)
                yield event
            span.finish(status="ok")
        except Exception as e:
            span.finish(status="error", error=str(e))
            raise
        finally:
            await self._emit_span(span)

    async def _emit_span(self, span: "AgentSpan") -> None:
        """POST span to AgentObservabilityCollector if collector_url set."""
        ...
```

---

### 4.3 `mindtrace/agents/plugins/` (no extra required)

#### `MindtracePluginRegistry`

```python
from mindtrace.core import Mindtrace

class SkillInfo(BaseModel):
    name: str
    version: str
    description: str
    entry_point: str

class ProviderInfo(BaseModel):
    name: str
    version: str
    model_ids: list[str]
    entry_point: str

class MindtracePluginRegistry(Mindtrace):
    """
    Discovers skills and model providers via Python entry-points.
    Called once at MindtraceAgentWorker startup.

    Entry-point groups:
        mindtrace.skills          → AbstractSkill subclasses
        mindtrace.model_providers → AbstractModelProviderPlugin subclasses
    """

    def __init__(self, **kwargs: Any) -> None:
        self._skills: dict[str, AbstractSkill] = {}
        self._providers: dict[str, AbstractModelProviderPlugin] = {}

    def discover(self) -> None:
        """Scan importlib.metadata.entry_points() for both groups."""
        ...

    def get_skill(self, name: str) -> "AbstractSkill": ...
    def get_provider(self, name: str) -> "AbstractModelProviderPlugin": ...
    def list_skills(self) -> list[SkillInfo]: ...
    def list_providers(self) -> list[ProviderInfo]: ...
```

#### `AbstractSkill`

```python
from mindtrace.agents.toolsets import AbstractToolset

class AbstractSkill(AbstractToolset[ToolAgentDepsT]):
    """
    Base class for skill plugins. Extends AbstractToolset so skills
    are drop-in toolsets with no agent-side changes required.

    Register via pyproject.toml:
        [project.entry-points."mindtrace.skills"]
        my_skill = "my_package.skills:MySkill"
    """

    @property
    @abstractmethod
    def skill_name(self) -> str: ...

    @property
    @abstractmethod
    def skill_version(self) -> str: ...

    @property
    def skill_description(self) -> str:
        return ""

    async def setup(self) -> None:
        """Called once by MindtracePluginRegistry after discovery."""
        ...

    async def teardown(self) -> None:
        """Called on worker shutdown."""
        ...
```

#### `AbstractModelProviderPlugin`

```python
from mindtrace.agents.providers import Provider

class AbstractModelProviderPlugin(Provider):
    """
    Base class for model provider plugins.

    Register via pyproject.toml:
        [project.entry-points."mindtrace.model_providers"]
        my_provider = "my_package.providers:MyProvider"
    """

    @property
    @abstractmethod
    def provider_name(self) -> str: ...

    @property
    @abstractmethod
    def supported_model_ids(self) -> list[str]: ...
```

---

## 5. Data Flow Diagrams

### 5.1 WebSocket Streaming: Client → Agent → Client

```
Machine A (Client)                Machine B (Gateway)              Machine C (Worker)
──────────────────                ───────────────────              ──────────────────
                                  MindtraceAgentGateway
                                    ↑
ws connect /ws/agents ────────────▶│
                                   │ auth → user_id
                                   │ assign session_id
◀── AgentSessionMessage ───────────│
                                   │
── AgentInvokeRequest ────────────▶│
   (agent_name, input,             │ create AgentRunContext
    session_id, stream=true)       │ build AgentTaskEnvelope
                                   │─ AMQP publish ──────────────▶ RabbitMQ queue
◀── AgentAckMessage (task_id) ─────│
                                   │                               MindtraceAgentWorker
                                   │                               consume envelope
                                   │                               _load_agent(name)
                                   │                               reconstruct RunContext
                                   │                               agent.run_stream_events()
                                   │                               │
                                   │                               ├─ PartStartEvent
                                   │                               │  └─ Redis PUBLISH
                                   │                               │     task:{task_id}
                                   │ Redis SUBSCRIBE ──────────────┤
                                   │ task:{task_id}                ├─ PartDeltaEvent × N
◀── AgentStreamEvent ──────────────│ relay each frame              │  └─ Redis PUBLISH
◀── AgentStreamEvent × N ──────────│                               │
                                   │                               ├─ ToolResultEvent
◀── AgentStreamEvent ──────────────│                               │  └─ Redis PUBLISH
                                   │                               │
                                   │                               └─ AgentRunResultEvent
                                   │                                  └─ Redis PUBLISH
                                   │                                     result:{task_id}
◀── AgentInvokeResponse ───────────│ read result:{task_id}
                                   │ UNSUBSCRIBE channel
── ws disconnect ─────────────────▶│
```

### 5.2 Memory Read/Write Across Machines

```
MindtraceAgentWorker (Machine C)
│
├── SHORT-TERM (session-scoped, volatile)
│   RedisMemoryStore(namespace="session:{session_id}")
│   ─── HSET/HGET/EXPIRE ──▶ Redis (shared infra, any machine)
│   TTL: 1h default, refreshed on write
│
└── LONG-TERM (persistent, searchable)
    MongoMemoryStore(namespace="agent:{name}:user:{user_id}")
    ─── insert/find ─────────▶ MongoDB (shared infra)
    │   with vector field if embedding_provider set
    │
    ├── vector search path:
    │   embed(query) → float[] → $vectorSearch aggregation
    └── text search fallback:
        $text: {$search: query}
```

### 5.3 Observability Span Collection

```
MindtraceAgentWorker (Machine C)
│  AgentObservabilityMixin wraps agent.run()
│  builds AgentSpan on start, records events, finishes on completion
│
│── POST /spans ──────────────────────────▶ AgentObservabilityCollector (Machine B or D)
                                               │
                                               ├── store in MongoDB (span history)
                                               │
                                               ├── batch export ──▶ OTLP endpoint
                                               │                    (Jaeger / Grafana Tempo)
                                               │
                                               └── update in-memory metrics counters
                                                   (Prometheus-format at GET /metrics)
```

### 5.4 Plugin Discovery on Worker Startup

```
MindtraceAgentWorker.__init__()
│
└── MindtracePluginRegistry.discover()
      │
      ├── importlib.metadata.entry_points("mindtrace.skills")
      │     ├── load WebSearchSkill    → instantiate → call setup()
      │     ├── load CalendarSkill     → instantiate → call setup()
      │     └── ...
      │
      └── importlib.metadata.entry_points("mindtrace.model_providers")
            ├── load CohereProvider   → register in provider map
            └── ...

[Worker ready — all skills available as toolsets, all providers available as models]

_load_agent("my_agent")
│  fetch AgentDefinition from MindtraceAgentRegistry
│  check required_skills ⊆ discovered skills
│  check required_provider ⊆ discovered providers
└── instantiate agent with skills injected as CompoundToolset
```

---

## 6. Memory & Context Architecture

### Memory Namespace Model

| Scope | Backend | Key Pattern | TTL | Use Case |
|---|---|---|---|---|
| per-task | Redis | `task:{task_id}:{key}` | task lifetime | Intermediate tool results, scratchpad within a single run |
| per-session | Redis | `session:{session_id}:{key}` | 1h (configurable) | Conversation working memory shared across turns of one session |
| per-user | MongoDB | `user:{user_id}:{key}` | permanent | User preferences, long-term facts, cross-session continuity |
| per-project | MongoDB | `project:{project_id}:{key}` | permanent | Camera config, defect classes, production line layout, training notes |
| per-org | MongoDB | `org:{org_id}:{key}` | permanent | Org-level context, compliance rules, shared knowledge base, team preferences |
| per-agent | MongoDB | `agent:{name}:{key}` | permanent | Agent-specific cached knowledge |
| global | MongoDB | `global:{key}` | permanent | Shared facts accessible to all agents, orgs, and users |

> **Memory injection on worker startup:** Before executing a task, `MindtraceAgentWorker._run_agent()` loads context from all relevant scopes in priority order: (1) session history via `RedisHistoryStrategy`, (2) session memory via `RedisMemoryStore`, (3) user memory (recent/pinned entries), (4) project memory (configuration keys), (5) org memory (policies and shared knowledge). Items from scopes 3–5 are surfaced as additional system context appended to the agent's system prompt — not injected into conversation history — so the agent can use them without the user seeing them. The worker limits context injection to entries tagged `inject=true` in metadata to avoid flooding the context window.

### Queue Topology and Session Routing

**Chosen model: shared queue with Redis-backed session state (no per-worker session affinity).**

The earlier design described per-worker queues with consistent-hashing session affinity. That model is incompatible with work-stealing and creates uneven load when one worker's session set is active while others are idle. It was therefore removed.

The architecture uses a **single shared RabbitMQ queue** (`mindtrace.agent.tasks`). Any available `MindtraceAgentWorker` may consume any task. Session continuity is maintained via shared external state rather than worker-local state:

- **Conversation history** — stored in `RedisHistoryStrategy` (keyed by `session_id`), readable by any worker.
- **Session memory** — stored in `RedisMemoryStore(namespace="session:{session_id}")`, also readable by any worker.
- **In-flight task state** — stored in Redis (`task:{task_id}`, `result:{task_id}`) before the worker is selected.

Because history and memory are stored externally, no worker needs to "own" a session. Any worker that picks up a task for `session_id=X` can load the full session context from Redis in one round-trip before beginning execution.

**Trade-off acknowledged:** this adds a Redis read on every task (one `LRANGE` for history + one `HGETALL` for session memory). The Redis reads are O(N) in message count and have sub-millisecond latency for typical session sizes (< 200 messages). The operational simplicity of a single queue, combined with the elimination of hot-worker risk, justifies this cost.

**If per-worker affinity is needed in future** (e.g., to keep large model weights warm in-process), introduce per-worker queues as a routing strategy selectable at `RabbitMQAgentTaskQueue` construction time — but the shared-queue model must remain the default.

```python
# How any worker loads session state — no affinity required:
history = await self.history_strategy.load(envelope.session_id)
session_mem = await self.memory_store.list_keys()   # namespace="session:{session_id}"
```

### `AgentRunContext` Wire Fields

| Field | Type | Description |
|---|---|---|
| `trace_id` | `str` | W3C TraceContext trace-id (32 hex chars) |
| `span_id` | `str` | W3C TraceContext parent-id (16 hex chars) |
| `session_id` | `str` | Routes history + session memory lookups (any worker, via shared Redis) |
| `user_id` | `str` | Routes user-scoped memory lookups and result access control |
| `org_id` | `str \| None` | Routes org-scoped memory lookups; `None` if request has no org context |
| `project_id` | `str \| None` | Routes project-scoped memory lookups; `None` if request has no project context |
| `run_id` | `str \| None` | Unique per `run()` call |
| `baggage` | `dict[str, str]` | W3C Baggage key=val pairs |
| `deps_json` | `str` | JSON-serialized deps (Pydantic model) |
| `deps_type_path` | `str` | Importable dotted path to deps type for deserialization |
| `step` | `int` | Tool call iteration counter |
| `retry` | `int` | Retry count for this task |

---

## 7. Authentication & Authorization Model

### Principals and Trust Boundaries

| Principal | How they authenticate | What they may do |
|---|---|---|
| **Human user** | Bearer JWT (OIDC) in WebSocket `Authorization` header or query param `token=` | Submit tasks, read their own results, disconnect own sessions |
| **Service account** | Shared HMAC-SHA256 API key in `X-Mindtrace-Api-Key` header | Submit tasks, read any task result, list agents |
| **Worker** | Shared internal secret (`MINDTRACE_INTERNAL_SECRET` env var) in `X-Mindtrace-Worker-Token` header | Register/heartbeat/deregister in MindtraceAgentRegistry; POST spans to collector |
| **Admin** | Service-account key with `role=admin` claim | Register/delete AgentDefinitions, manage allowlist, drain DLQ |

No unauthenticated requests are permitted on any endpoint. The gateway and collector enforce authentication on every connection.

### JWT Validation (`MindtraceAgentGateway._authenticate`)

```python
async def _authenticate(self, websocket: WebSocket) -> AuthenticatedPrincipal:
    """
    Extract and validate credentials from the WebSocket upgrade request.

    Token precedence (first match wins):
      1. Authorization header: "Bearer <jwt>"
      2. Query parameter: ?token=<jwt>
      3. X-Mindtrace-Api-Key header: <hmac_key>

    Returns:
        AuthenticatedPrincipal with user_id, role, and scopes.

    Raises:
        AuthenticationError: token missing, expired, or invalid signature.
        AuthorizationError: token valid but principal lacks required scope.
    """
    ...
```

```python
class AuthenticatedPrincipal(BaseModel):
    """Verified identity attached to every authenticated request."""
    principal_id: str                        # user_id or service account ID
    principal_type: Literal["user", "service", "worker", "admin"]
    role: str
    scopes: list[str]                        # e.g. ["tasks:submit", "tasks:read", "agents:list"]
    token_expires_at: datetime | None = None
```

### Authorization Scopes

| Scope | Required for |
|---|---|
| `tasks:submit` | POST /agents/{name}/invoke, WS AgentInvokeRequest |
| `tasks:read` | GET /agents/{name}/tasks/{task_id}, GET result |
| `tasks:cancel` | cancel() on RabbitMQAgentTaskQueue |
| `agents:list` | GET /agents/ |
| `agents:manage` | Register/delete AgentDefinition (admin only) |
| `dlq:manage` | Inspect and requeue from DLQ (admin only) |
| `allowlist:manage` | Add/remove entries from MindtraceAllowlistRegistry (admin only) |
| `spans:ingest` | POST /spans on AgentObservabilityCollector (worker only) |
| `metrics:read` | GET /metrics on AgentObservabilityCollector |

### How Permissions Are Enforced

1. **Gateway layer** — `_authenticate()` runs before any WebSocket frame is processed or REST handler is called. The returned `AuthenticatedPrincipal` is attached to the request state. Route handlers call `require_scope(principal, "tasks:submit")` (a thin guard utility) and raise `AuthorizationError` if the scope is absent.

2. **Envelope layer** — `TaskProvenance.submitter_id` and `submitter_role` are written from the authenticated principal at envelope creation time. Workers treat provenance as read-only; they do not re-authenticate the submitter, but they log it in the `AgentSpan` for audit.

3. **Registry layer** — `MindtraceAgentRegistry.register_agent()` requires the caller to present an `admin`-role token. The registry validates this via the internal secret, not via the gateway.

4. **Result access** — A user-scoped principal may only call `get_result(task_id)` for tasks they submitted (enforced by checking `provenance.submitter_id == principal.principal_id`). Service accounts and admins may access any result.

### Token Issuance

Mindtrace does not issue tokens; it validates them. The expected deployment is:

- **OIDC / OAuth2**: An external identity provider (e.g., Keycloak, Auth0) issues JWTs. The gateway verifies the signature using the JWKS endpoint configured via `MINDTRACE_JWKS_URL` env var.
- **API keys**: The gateway generates an HMAC-SHA256 key on first admin setup, stored in Redis at `mindtrace:apikeys:{key_hash}`. Key metadata (role, scopes, expiry) is stored alongside the hash.

Both token types share the same `AuthenticatedPrincipal` schema once validated.

### Worker-to-Registry Authentication

Workers present `MINDTRACE_INTERNAL_SECRET` (a 256-bit random value, set as an environment variable on every node) in `X-Mindtrace-Worker-Token`. The registry validates the header with a constant-time compare. This secret must be rotated via the deployment orchestration layer (Kubernetes secret, Docker secret), not hard-coded.

---

## 8. Failure, Retry & Dead-Letter Semantics

### Failure Classification

| Failure type | Retryable? | Reason |
|---|---|---|
| Transient infrastructure error (Redis/RabbitMQ timeout, network blip) | Yes | Recoverable with backoff |
| Worker process crash (OOM, unhandled exception outside agent) | Yes | New worker will pick up re-enqueued task |
| Agent execution error (`Exception` from `agent.run()`) | Configurable (default: No) | Application logic errors are usually deterministic; retrying wastes tokens |
| Task TTL exceeded (task_ttl_seconds elapsed before worker picks it up) | No — route to DLQ | Stale context; client has likely given up |
| `AllowlistViolationError` (agent_class or deps_type_path not in allowlist) | No — drop and alert | Security violation; retrying will always fail and may indicate an attack |
| `AuthenticationError` / `AuthorizationError` | No — reject immediately | Credential problem; retrying will always fail |
| `ValidationError` (malformed envelope) | No — route to DLQ | Schema mismatch; retrying will always fail |

### Retry Policy

```python
class RetryPolicy(BaseModel):
    """
    Configurable per-queue retry policy. Passed to RabbitMQAgentTaskQueue
    and RedisAgentTaskQueue at construction time.
    """
    max_retries: int = 3
    backoff_strategy: Literal["fixed", "exponential", "jitter"] = "exponential"
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 60.0
    jitter_factor: float = 0.2             # ± 20% random jitter on exponential delay
    retry_on_agent_error: bool = False     # if True, agent-raised exceptions are retried
```

**Backoff formula (exponential with jitter):**

```
delay = min(base_delay * 2^attempt, max_delay) * uniform(1 - jitter, 1 + jitter)
```

### Retry Execution

1. When a worker decides to retry a task, it increments `AgentTaskEnvelope.retry_count` and re-publishes the envelope to the main queue with a `delay` header (RabbitMQ delayed-message plugin) or a deferred `ZADD` (Redis sorted set by next-execute-at timestamp).
2. If `retry_count >= max_retries`, the envelope is published to the DLQ instead.
3. Workers check `retry_count` against `max_retries` before beginning execution; a message that arrived at the worker with an already-exhausted retry count is immediately routed to the DLQ.

### Dead-Letter Queue (DLQ) Design

```
Exchange:   mindtrace.agent.tasks.dlq
Queue:      mindtrace.agent.tasks.dlq
Routing:    all exhausted/fatal envelopes; RabbitMQ x-dead-letter-exchange config
```

Each DLQ message is augmented with a `DLQRecord` header:

```python
class DLQRecord(BaseModel):
    original_task_id: str
    failure_reason: str                    # human-readable error message
    failure_type: str                      # e.g. "agent_error", "ttl_exceeded", "allowlist_violation"
    failed_at: datetime
    retry_count: int
    worker_id: str
    node_id: str
```

**DLQ operations** (admin scope `dlq:manage`):

| Operation | Description |
|---|---|
| `inspect_dlq()` | List DLQ messages with DLQRecord metadata |
| `requeue_from_dlq(task_id)` | Reset `retry_count` to 0, re-publish to main queue |
| `purge_dlq()` | Delete all DLQ messages (irreversible) |

`requeue_from_dlq` is intentionally manual for `AllowlistViolationError` and `ValidationError` failures — an operator must inspect and confirm the re-enqueue is safe before the task is retried.

### Worker-Side Execution Guard

```python
# MindtraceAgentWorker._run_agent() — first lines before any agent execution:

envelope = AgentTaskEnvelope.model_validate(job_dict)

# 1. Check task TTL
age_seconds = (datetime.utcnow() - envelope.submitted_at).total_seconds()
if age_seconds > envelope.task_ttl_seconds:
    await self._route_to_dlq(envelope, reason="ttl_exceeded")
    return

# 2. Check allowlist before any import
from mindtrace.agents.distributed.allowlist import MindtraceAllowlistRegistry
MindtraceAllowlistRegistry.enforce_agent_class(envelope.run_context... )
# raises AllowlistViolationError → caught → route to DLQ, do NOT retry
```

---

## 9. Circuit-Breaker & Backpressure

### Problem

Without flow control, a slow or unresponsive downstream (overloaded worker pool, Redis, MongoDB, RabbitMQ) can cause cascading failures: the gateway accumulates in-flight WebSocket sessions, the queue grows unbounded, and workers begin OOM-crashing under combined memory pressure.

### Circuit-Breaker on the Gateway

`MindtraceAgentGateway` maintains one circuit-breaker per logical dependency: the task queue, the agent registry, and the observability collector.

```python
class CircuitState(Enum):
    CLOSED = "closed"       # normal operation
    OPEN = "open"           # failing fast; no calls pass through
    HALF_OPEN = "half_open" # probe state; one call allowed to test recovery

class CircuitBreaker:
    """
    Lightweight circuit-breaker wrapping async callables.

    Transitions:
        CLOSED → OPEN   : failure_count >= failure_threshold within window_seconds
        OPEN → HALF_OPEN: after recovery_timeout_seconds
        HALF_OPEN → CLOSED: probe call succeeds
        HALF_OPEN → OPEN: probe call fails; reset recovery timer

    All state is in-process (per gateway instance). For multi-gateway deployments,
    use a shared Redis key for the open/half-open state if consistent fast-fail is needed.
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,         # failures within window before opening
        window_seconds: float = 30.0,
        recovery_timeout_seconds: float = 60.0,
    ) -> None: ...

    async def call(self, fn: Callable[..., Awaitable[T]], *args: Any, **kwargs: Any) -> T:
        """
        Wrap an async call with circuit-breaker logic.

        Raises:
            CircuitOpenError: if the circuit is OPEN and recovery_timeout has not elapsed.
        """
        ...
```

The gateway wraps queue publish calls:

```python
# MindtraceAgentGateway — task submission path:
try:
    task_id = await self._queue_breaker.call(self.task_queue.submit, envelope)
except CircuitOpenError:
    await websocket.send_json(AgentErrorMessage(
        code="service_unavailable",
        message="Task queue is temporarily unavailable. Retry in a few seconds.",
        trace_id=envelope.run_context.trace_id,
    ).model_dump())
    return
```

### Backpressure at the Gateway

Two complementary limits prevent the gateway from accepting work it cannot route:

**1. Concurrent session limit**

```python
# Configured at MindtraceAgentGateway construction:
max_concurrent_sessions: int = 500  # default; reject new WS connections beyond this

# Enforced in websocket_endpoint():
if len(self._active_sessions) >= self.max_concurrent_sessions:
    await websocket.close(code=1013, reason="server_overloaded")
    return
```

**2. Queue depth check before publish**

Before publishing a new task envelope, the gateway queries the RabbitMQ management API (or a Redis `LLEN` for `RedisAgentTaskQueue`) for current queue depth. If depth exceeds `max_queue_depth`, the task is rejected with a `503`-equivalent error message rather than enqueued:

```python
class BackpressureConfig(BaseModel):
    max_queue_depth: int = 10_000           # tasks; reject new submissions above this
    max_concurrent_sessions: int = 500      # WS sessions per gateway instance
    queue_depth_check_interval_seconds: float = 5.0  # cache queue depth to avoid per-request RPC
```

### Backpressure at the Worker

Workers implement a local semaphore limiting concurrent agent executions:

```python
# MindtraceAgentWorker — concurrency guard:
self._execution_semaphore = asyncio.Semaphore(max_concurrent_agents)  # default: 4

async def _run_agent(self, envelope: AgentTaskEnvelope) -> Any:
    async with self._execution_semaphore:
        ...  # agent execution
```

If the semaphore is exhausted (all `max_concurrent_agents` slots occupied), the worker stops calling `basic_get` / `BRPOP` — it does not NACK in-flight messages; it simply stops consuming until a slot frees. This provides natural back-pressure to the queue without message loss.

### Metrics for Circuit-Breaker and Backpressure

The following metrics are added to `AgentObservabilityCollector` (see Section 10):

| Metric | Type | Labels | Description |
|---|---|---|---|
| `gateway_circuit_state` | Gauge (0/1/2) | `gateway_id`, `dependency` | Circuit state (0=closed, 1=open, 2=half_open) |
| `gateway_sessions_active` | Gauge | `gateway_id` | Active WebSocket sessions |
| `gateway_tasks_rejected_total` | Counter | `gateway_id`, `reason` | Tasks rejected by backpressure or circuit-breaker |
| `worker_execution_slots_available` | Gauge | `worker_id` | Available concurrency slots |

---

## 10. Observability Design

### `AgentSpan`

```python
@dataclass
class ToolCallRecord:
    tool_name: str
    tool_call_id: str
    args_preview: str            # first 200 chars of JSON args
    result_preview: str          # first 200 chars of result
    duration_ms: float
    success: bool

@dataclass
class AgentSpan:
    # Identity
    trace_id: str
    span_id: str
    parent_span_id: str | None

    # Agent context
    agent_name: str
    worker_id: str
    node_id: str
    session_id: str
    user_id: str

    # Timing
    started_at: datetime
    ended_at: datetime | None
    duration_ms: float | None

    # Outcome
    status: Literal["ok", "error"]
    error: str | None

    # Content previews (truncated to 200 chars for privacy)
    input_preview: str
    output_preview: str | None

    # Token usage
    input_tokens: int
    output_tokens: int
    model_name: str

    # Tool calls
    tool_calls: list[ToolCallRecord]

    # Memory operations
    memory_reads: int
    memory_writes: int
    history_loads: int

    @classmethod
    def start(cls, agent_name: str, worker_id: str, ...) -> "AgentSpan": ...
    def finish(self, status: str, output: Any = None, error: str | None = None) -> None: ...
    def record_event(self, event: NativeEvent) -> None: ...
    def to_otlp(self) -> dict: ...     # OTLP JSON span format (OpenTelemetry-compatible)
```

### Metrics Exposed by `AgentObservabilityCollector`

| Metric | Type | Labels | Description |
|---|---|---|---|
| `agent_run_duration_seconds` | Histogram | `agent_name`, `worker_id`, `status` | End-to-end run latency |
| `agent_runs_total` | Counter | `agent_name`, `status` | Total invocations |
| `agent_tool_calls_total` | Counter | `agent_name`, `tool_name`, `status` | Tool invocation counts |
| `agent_tokens_total` | Counter | `agent_name`, `direction` (input\|output) | Token consumption |
| `agent_memory_ops_total` | Counter | `agent_name`, `op` (read\|write), `store` (redis\|mongo) | Memory operations |
| `agent_active_sessions` | Gauge | `agent_name` | Live sessions |
| `worker_queue_depth` | Gauge | `worker_id` | Pending tasks per worker |

### Span Transport

```
AgentObservabilityMixin._emit_span(span)
  └── if collector_url:
        POST {collector_url}/spans   (JSON body: span.model_dump())
      else:
        log span as structured JSON (mindtrace structured logger)
```

### OpenTelemetry Trace Propagation

Distributed traces are threaded through the system using W3C TraceContext headers. The `AgentRunContext` carries `trace_id` and `span_id` (W3C traceparent format) from the gateway through the queue into the worker. Workers create a child span using these identifiers, ensuring the full request tree is visible in Jaeger / Grafana Tempo.

```
Client request
  └── Gateway span (trace_id=T, span_id=G)
        └── Worker span (trace_id=T, parent_span_id=G, span_id=W)
              └── Tool call spans (trace_id=T, parent_span_id=W)
```

The `AgentSpan.to_otlp()` method serializes spans in OTLP JSON format. The `AgentObservabilityCollector` batches these and forwards them to the configured OTLP endpoint (`otlp_endpoint` parameter, e.g. `http://jaeger:4318/v1/traces`).

To propagate trace context across the RabbitMQ message boundary, the envelope's `run_context` fields are the carrier — no additional OTel SDK dependency is required on the worker.

### Health Check Interfaces

Every service component (`MindtraceAgentGateway`, `MindtraceAgentWorker`, `AgentObservabilityCollector`, `MindtraceAgentRegistry`) exposes a `GET /health` endpoint returning a `HealthStatus` model:

```python
class ComponentHealth(BaseModel):
    name: str
    status: Literal["ok", "degraded", "down"]
    latency_ms: float | None = None          # last probe round-trip time
    message: str | None = None              # human-readable detail on degraded/down

class HealthStatus(BaseModel):
    """Returned by GET /health on any Mindtrace distributed service."""
    service: str                             # e.g. "MindtraceAgentGateway"
    instance_id: str                         # unique per process
    status: Literal["ok", "degraded", "down"]
    components: list[ComponentHealth]        # per-dependency probe results
    uptime_seconds: float
    version: str
```

**Gateway health components checked:** RabbitMQ connectivity, Redis connectivity, `MindtraceAgentRegistry` reachability, circuit-breaker states.

**Worker health components checked:** Redis Pub/Sub connectivity, `MindtraceAgentRegistry` reachability, `AgentObservabilityCollector` reachability, execution semaphore availability.

The `GET /health` endpoint is unauthenticated (no scope required) to allow load-balancer and Kubernetes liveness/readiness probes without credentials. It must not return sensitive data (no keys, URLs, or internal IPs in responses).

---

## 11. Agent & Dependency Class Allowlist Registry

### Problem

Both `AgentRunContext.deps_type_path` and `AgentDefinition.agent_class` accept dotted import paths that are used to load Python classes at runtime. If an attacker can control either value (via a malicious task submission or a compromised registry entry), they can cause arbitrary code to be loaded and instantiated on the worker — a remote code execution (RCE) vector.

### Solution: `MindtraceAllowlistRegistry`

All class paths are validated against a server-side allowlist before any `import` or `importlib` call is made. Paths not on the allowlist are rejected with `AllowlistViolationError`; the envelope is routed to the DLQ (see Section 8). No retry is attempted.

```python
# mindtrace/agents/distributed/allowlist.py

class AllowlistEntry(BaseModel):
    """A single permitted class path in the allowlist."""
    dotted_path: str                         # e.g. "myapp.agents:MyAgent" or "myapp.deps:MyDeps"
    entry_type: Literal["agent_class", "deps_type"]
    registered_by: str                       # principal_id of admin who added this entry
    registered_at: datetime
    description: str | None = None

class AllowlistViolationError(Exception):
    """Raised when a class path is not found in the allowlist."""
    def __init__(self, path: str, entry_type: str) -> None:
        super().__init__(
            f"Class path '{path}' (type={entry_type}) is not in the Mindtrace allowlist. "
            "An admin must register it via 'mindtrace agents allowlist-add' before use."
        )
        self.path = path
        self.entry_type = entry_type

class MindtraceAllowlistRegistry:
    """
    Redis-backed allowlist of permitted agent_class and deps_type paths.

    Storage: Redis hash  mindtrace:allowlist:{entry_type} → {dotted_path: JSON(AllowlistEntry)}
    Access: read by workers (unauthenticated internal network); write requires admin scope.

    The registry is intentionally simple: no wildcards, no glob patterns.
    Each permitted path must be explicitly registered. This is a security
    boundary, not a convenience API.
    """

    def __init__(self, redis_url: str) -> None: ...

    # ── Write operations (admin scope required at the HTTP layer) ──────────

    async def register(self, entry: AllowlistEntry) -> None:
        """Add entry to the allowlist. Idempotent (overwrites existing)."""
        ...

    async def deregister(self, dotted_path: str, entry_type: str) -> None:
        """Remove entry. Raises KeyError if not found."""
        ...

    # ── Read operations (called by workers — no auth required internally) ──

    async def is_permitted(self, dotted_path: str, entry_type: str) -> bool:
        """Return True if the path is in the allowlist."""
        ...

    async def enforce_agent_class(self, dotted_path: str) -> None:
        """
        Raise AllowlistViolationError if dotted_path is not an allowed agent_class.
        Called by MindtraceAgentWorker._load_agent() before any import.
        """
        if not await self.is_permitted(dotted_path, "agent_class"):
            raise AllowlistViolationError(dotted_path, "agent_class")

    async def enforce_deps_type(self, dotted_path: str) -> None:
        """
        Raise AllowlistViolationError if dotted_path is not an allowed deps_type.
        Called by AgentRunContext.to_run_context() before any import.
        """
        if not await self.is_permitted(dotted_path, "deps_type"):
            raise AllowlistViolationError(dotted_path, "deps_type")

    async def list_entries(
        self, entry_type: str | None = None
    ) -> list[AllowlistEntry]:
        """List all entries, optionally filtered by type."""
        ...
```

### Enforcement Points

| Where | What is checked | Action on violation |
|---|---|---|
| `MindtraceAgentRegistry.register_agent()` | `definition.agent_class` | Reject registration; return HTTP 422 |
| `MindtraceAgentWorker._load_agent()` | `definition.agent_class` (re-checked at load time) | `AllowlistViolationError` → DLQ, no retry |
| `AgentRunContext.to_run_context()` | `self.deps_type_path` | `AllowlistViolationError` → DLQ, no retry |

Re-checking at load time (in addition to registration time) defends against allowlist entries being removed after an agent was registered, or registry data being tampered with directly in Redis.

### Default Entries

On first startup, `MindtraceAllowlistRegistry` seeds two built-in entries:

```python
AllowlistEntry(dotted_path="builtins.NoneType", entry_type="deps_type", ...)
AllowlistEntry(dotted_path="pydantic.BaseModel", entry_type="deps_type", ...)
```

All application-specific agent classes and deps types must be explicitly added by an admin.

### CLI Management

```bash
# Add a permitted agent class
mindtrace agents allowlist-add --path "myapp.agents:MyAgent" --type agent_class

# Add a permitted deps type
mindtrace agents allowlist-add --path "myapp.deps:MyDeps" --type deps_type

# List all entries
mindtrace agents allowlist-list

# Remove an entry
mindtrace agents allowlist-remove --path "myapp.agents:OldAgent" --type agent_class
```

---

## 12. Plugin System

The plugin system lives in `mindtrace/agents/plugins/` — no extra installation required. Any installed package can register skills and model providers by declaring entry-points; `MindtraceAgentWorker` discovers them at startup.

### Registration (third-party package)

```toml
# In any third-party skill or provider package's pyproject.toml:

[project.entry-points."mindtrace.skills"]
web_search  = "my_package.skills:WebSearchSkill"
calendar    = "my_package.skills:CalendarSkill"

[project.entry-points."mindtrace.model_providers"]
cohere      = "my_package.providers:CohereProvider"
```

A `pip install my-skill-package` is the only step required. Workers discover it on next startup.

### Discovery Sequence

```python
# mindtrace/agents/plugins/registry.py — MindtracePluginRegistry.discover():

from importlib.metadata import entry_points

for ep in entry_points(group="mindtrace.skills"):
    cls = ep.load()                    # import the AbstractSkill subclass
    instance = cls()                   # instantiate
    await instance.setup()             # async setup (auth, connections, etc.)
    self._skills[instance.skill_name] = instance

for ep in entry_points(group="mindtrace.model_providers"):
    cls = ep.load()
    instance = cls()
    self._providers[instance.provider_name] = instance
```

### Skill Injection into Agents

```python
# mindtrace/agents/distributed/worker.py — MindtraceAgentWorker._load_agent():

definition = await self.agent_registry.get_agent_definition(agent_name)

required_toolsets = [
    self.plugin_registry.get_skill(skill_name)
    for skill_name in definition.required_skills
]
compound = CompoundToolset(*required_toolsets) if required_toolsets else None

# Enforce allowlist BEFORE any import — AllowlistViolationError routes to DLQ
await self.allowlist_registry.enforce_agent_class(definition.agent_class)

agent_cls = import_class(definition.agent_class)  # safe: path is allowlisted
agent = agent_cls(
    **definition.init_kwargs,
    toolset=compound,
)
```

---

## 13. Implementation Tasks

| # | Title | Location | Extra required | Depends On | Size | Acceptance Criteria |
|---|---|---|---|---|---|---|
| 01 | `AgentRunContext` + `AgentTaskEnvelope` (incl. `TaskProvenance`) | `agents/context/propagation.py` | none | — | S | Serialize/deserialize with no field loss; W3C traceparent header round-trips; `to_run_context()` validates `deps_type_path` against allowlist before importing; `TaskProvenance` fields present on all envelopes |
| 02 | `MindtraceAllowlistRegistry` | `agents/distributed/allowlist.py` | `distributed-cluster` | 01 | M | Default entries populated; `enforce_agent_class` raises `AllowlistViolationError` for unregistered path; admin API adds/removes entries; allowlist persisted in Redis |
| 03 | `RabbitMQAgentTaskQueue` (with `RetryPolicy`) | `agents/execution/rabbitmq.py` | `distributed-rabbitmq` | 01 | M | submit/get_result round-trip; DLQ captures exhausted tasks; `requeue_from_dlq` retries; exponential backoff delay tested; `task_ttl_seconds` respected |
| 04 | `RedisAgentTaskQueue` | `agents/execution/redis.py` | `memory-redis` | 01 | M | submit/get_result with TTL expiry tested; cancel flag respected before worker picks up task |
| 05 | `RedisHistoryStrategy` | `agents/history/redis.py` | `memory-redis` | — | M | load/save/clear tested; two concurrent sessions do not pollute each other; TTL resets on save |
| 06 | `RedisMemoryStore` | `agents/memory/redis.py` | `memory-redis` | — | M | save/get/delete/list_keys tested; namespace isolation verified; per-entry TTL override works |
| 07 | `MongoMemoryStore` (text search) | `agents/memory/mongo.py` | `memory-mongo` | — | M | save/search with `$text`; namespace isolation tested; correct top_k returned |
| 08 | `MongoMemoryStore` (vector search) | `agents/memory/mongo.py` | `memory-mongo` | 07 | L | `EmbeddingProvider` Protocol verified; Atlas vector index query tested; graceful fallback to `$text` when no provider |
| 09 | `AgentSpan` + `AgentObservabilityMixin` | `agents/observability/span.py` | none | 01 | M | Span emitted for both `run()` and `run_stream_events()`; token counts captured; `isinstance(agent, AbstractMindtraceAgent)` still passes |
| 10 | `AbstractSkill` + `MindtracePluginRegistry` | `agents/plugins/` | none | — | M | Entry-point discovery loads skills; `setup()`/`teardown()` called; skill usable as toolset in `MindtraceAgent` |
| 11 | `AbstractModelProviderPlugin` | `agents/plugins/providers.py` | none | 10 | S | Provider loaded and queryable; `supported_model_ids` returned correctly |
| 12 | `MindtraceAgentRegistry` | `agents/distributed/registry.py` | `distributed-cluster` | — | M | register/find/heartbeat tested; worker evicted after 3 missed heartbeats; `register_agent()` rejects `agent_class` not in allowlist; concurrent register/find is safe |
| 13 | Auth/authz middleware (`AuthenticatedPrincipal`, `require_scope`) | `agents/distributed/auth.py` | `distributed-cluster` | — | M | JWT validation against JWKS tested; HMAC API key validation tested; `require_scope` raises `AuthorizationError` for insufficient scope; result access blocked for non-owner user |
| 14 | `AgentObservabilityCollector` (incl. health endpoint) | `agents/distributed/collector.py` | `distributed-cluster` | 09 | M | POST /spans ingests and stores; GET /metrics returns Prometheus text format; OTLP export fires when `otlp_endpoint` set; GET /health returns component statuses |
| 15 | `CircuitBreaker` + `BackpressureConfig` | `agents/distributed/resilience.py` | `distributed-cluster` | — | M | Circuit opens after `failure_threshold` failures in window; recovers after `recovery_timeout`; gateway rejects new sessions at `max_concurrent_sessions`; worker semaphore limits concurrency |
| 16 | `MindtraceAgentWorker` (with TTL guard, allowlist check, retry) | `agents/distributed/worker.py` | `distributed-cluster` | 03, 05, 06, 09, 10, 12, 02 | L | Loads agent by name after allowlist check; respects `task_ttl_seconds`; applies `RetryPolicy`; publishes events to Redis Pub/Sub; span posted to collector; result written with `result_ttl_seconds` |
| 17 | `MindtraceAgentNode` | `agents/distributed/node.py` | `distributed-cluster` | 16 | S | Launches `MindtraceAgentWorker` subprocess; worker auto-registers in `MindtraceAgentRegistry` on start |
| 18 | `MindtraceAgentGateway` REST endpoints (with auth) | `agents/distributed/gateway.py` | `distributed-cluster` | 03, 12, 13 | M | POST /agents/{name}/invoke requires `tasks:submit` scope; result read enforces submitter check; 401/403 returned for missing/insufficient credentials |
| 19 | `MindtraceAgentGateway` WebSocket endpoint (with auth, backpressure) | `agents/distributed/gateway.py` | `distributed-cluster` | 18, 15 | L | WS connect/auth/invoke/stream/disconnect tested; circuit-breaker fires `service_unavailable` error frame; overload drops connection with code 1013; NativeEvents relayed in order |
| 20 | Update `pyproject.toml` extras | `mindtrace-agents/pyproject.toml` | — | all | S | `[distributed-cluster]`, `[memory-mongo]`, `[distributed]` extras install correctly; import guards raise `ImportError` with helpful message when extra missing |
| 21 | CLI commands (`mindtrace agents distributed`) | `agents/distributed/cli.py` | `distributed-cluster` | 17, 19 | M | `launch-gateway`, `launch-node`, `agent-status`, `list-agents`, `inspect-dlq`, `allowlist-add`, `allowlist-list` commands work end-to-end |
| 22 | E2E integration test suite | `tests/integration/` | `distributed` | all | L | Docker Compose: gateway + node + worker on separate services; auth enforced; circuit-breaker trips under injected failures; client streams over WS; span appears in collector; session + user memory persists across turns and restarts; `AllowlistViolationError` routes to DLQ; project/org memory injected into agent context |
| 23 | `MongoMemoryStore` org + project scopes | `agents/memory/mongo.py` | `memory-mongo` | 07 | S | `org:{org_id}:{key}` and `project:{project_id}:{key}` namespace isolation tested; org memory accessible to all users sharing same `org_id`; search returns correct top_k per namespace |
| 24 | Memory Management REST API | `agents/distributed/memory_api.py` | `distributed-cluster` | 06, 07, 23 | M | CRUD endpoints for session/user/project/org scopes; scope-based auth enforced (own user, org:member, org:admin); session memory returns 404 after TTL; search endpoint proxies `MongoMemoryStore.search()` or `RedisMemoryStore.search()`; memory injection at task start uses `inject=true` metadata tag |
| 25 | Session History REST API | `agents/distributed/gateway.py` | `distributed-cluster` | 05, 12 | S | `GET /sessions/{id}/history` returns deserialized messages in order; `DELETE /sessions/{id}/history` clears Redis key; `GET /sessions?user_id={id}` returns paginated list of session keys for that user |

---

## 14. Design Decisions & Trade-offs

### Gateway Connection: WebSocket + REST

WebSocket is chosen for the client-facing gateway connection because:
- `NativeEvent` stream (token-by-token) requires server-push; WebSocket is bidirectional and persistent
- Session state lives across multiple messages (multi-turn agents); HTTP would require repeated auth and session headers
- No polling overhead vs SSE; full-duplex vs HTTP/2 push
- WebSocket is composable with FastAPI (`websockets` library) which `Service` already uses

REST (`POST /agents/{name}/invoke`) is retained as a fallback for:
- Simple one-shot invocations that don't need streaming
- Clients in environments where WebSocket is not available
- Integration testing

### NativeEvent Relay: Redis Pub/Sub over Redis Streams

Pub/Sub is chosen over Redis Streams for the worker-to-gateway relay because:
- The gateway subscribes exactly once per task (1:1 relationship); no consumer groups needed
- Fire-and-forget semantics are acceptable — if the gateway restarts mid-stream, the client re-invokes (history is persisted in `RedisHistoryStrategy`)
- Pub/Sub has lower overhead than Streams for short-lived per-task channels

### Observability: MRO Mixin over Decorator

`AgentObservabilityMixin` uses Python MRO rather than a decorator wrapping agent methods because:
- A decorator wrapping `agent.run()` would break `isinstance(agent, AbstractMindtraceAgent)` checks used elsewhere in the codebase
- MRO placement in `MindtraceAgentWorker(AgentObservabilityMixin, Worker)` keeps span logic in the worker layer, not the agent layer — agents stay pure
- No modifications to `AbstractMindtraceAgent`, `MindtraceAgent`, or any existing agent subclass

### Span Transport: HTTP POST to Collector

Workers POST spans to `AgentObservabilityCollector` rather than running an OTel SDK in-process because:
- Keeps OTel thread pools and exporters out of the worker process
- Isolates observability failures from agent execution — if the collector is down, spans are dropped (logged locally), not agent runs
- Collector is the single OTLP emission point, simplifying configuration

### Queue Model: Shared Queue over Per-Worker Session-Affinity Queues

The v1.1 draft described per-worker queues with consistent-hashing session affinity. This was removed in v1.2 because:
- Work-stealing is incompatible with fixed per-worker queues — a hot worker stalls while others are idle.
- Consistent hashing breaks when workers are added or removed (hash ring rehashing required).
- Session state is already stored externally in Redis (history, memory); no worker-local session state exists to protect.

The shared-queue model (one `mindtrace.agent.tasks` queue, any worker may consume any task) was chosen as it is simpler to operate, scales horizontally without configuration changes, and loses nothing given the external session-state design. See Section 6 for full rationale.

### Allowlist Registry: Explicit Allowlist over Import Sandboxing

Python's import system does not provide a safe sandboxing mechanism for arbitrary dotted paths. Alternatives considered:

- **Subprocess isolation** (run each agent in a fresh subprocess): adds 200–500 ms cold-start latency; impractical for streaming token delivery.
- **AST analysis of dotted paths**: brittle; does not prevent loading of malicious pre-installed packages.
- **Explicit allowlist** (chosen): O(1) Redis lookup; zero false negatives; admin-controlled; auditable.

The trade-off is operational overhead: every new agent class and deps type must be explicitly registered. This is acceptable because agent deployments are infrequent and controlled operations, not developer self-service.

### Plugin Discovery: Python Entry-Points

Entry-points are chosen over a central plugin server because:
- `pip install my-skill-package` is the only operation required to register a skill
- Workers stay stateless with respect to plugin configuration
- Standard Python mechanism; works with all package managers (pip, uv, poetry)

### No New Packages — Optional Extras Instead

All distributed agent components land inside the two existing packages (`mindtrace-agents`, `mindtrace-cluster`) via optional extras rather than introducing new packages. This was the key structural decision:

- `mindtrace-agents` is currently lean (`openai + pydantic + mindtrace-core`). Adding `mindtrace-cluster` as a hard dependency would force all agent users to install `docker`, `mindtrace-database`, `mindtrace-jobs`, etc. — even for simple local use.
- The reverse (adding `mindtrace-agents` as a hard dep to `mindtrace-cluster`) has the same problem in the other direction.
- **Optional extras solve both problems**: `mindtrace-agents[distributed-cluster]` pulls in `mindtrace-cluster` only for users who need distributed deployment, keeping the base install lean.
- This follows the existing pattern in `mindtrace-agents/pyproject.toml` which already defines `mcp`, `distributed-rabbitmq`, `memory-redis`, `memory-vector` as optional extras.
- The gateway, worker, node, and registry live in `mindtrace/agents/distributed/` — guarded by an import check that raises `ImportError` with a helpful message if `[distributed-cluster]` is not installed.

### Terminology Conventions

This document uses the following terms consistently:

| Term | Meaning |
|---|---|
| **agent** | A `MindtraceAgent` / `AbstractMindtraceAgent` instance — the unit of AI logic. Agents do not know about distribution. |
| **worker** | A `MindtraceAgentWorker` process — the distributed runtime that loads and executes agents on a remote machine. One worker process may run multiple agents sequentially. |
| **node** | A `MindtraceAgentNode` — a machine (VM or container) that manages one or more worker processes. |
| **gateway** | `MindtraceAgentGateway` — the network entry point; routes client requests to workers via the task queue. |
| **task** | A unit of work: one `AgentTaskEnvelope` flowing through the queue to a worker. |
| **session** | A multi-turn conversation identified by `session_id`. Sessions span multiple tasks but have no dedicated worker (shared-queue model). |

The term "worker" is never used to mean "agent". The term "agent" is never used to mean "worker process".

### Assumptions (confirm with team)

1. `AgentCallbacks` in `MindtraceAgent.__init__` fires on tool calls and usage events — required for `_ObservabilityCallbacks` to capture token counts without patching agent internals.
2. `Worker._run()` is called from a thread (not inside an asyncio event loop) — the `asyncio.get_event_loop().run_until_complete()` bridge in `MindtraceAgentWorker._run()` assumes this. If `Worker` already runs `_run()` inside an event loop, replace the bridge with a direct `await`.
3. `Gateway` mounts on an ASGI application that accepts additional route registrations at startup — the WebSocket and REST endpoints assume `Service.add_endpoint()` is callable in `__init__`.

---

## 15. Memory Management API

This section describes the dedicated HTTP endpoints for reading and writing memory across all scopes. These endpoints live in `agents/distributed/memory_api.py` and are registered on the gateway at startup (requires `[distributed-cluster]` extra). They complement the WebSocket/tool-based memory access with a management API usable by the Chiron admin UI and service-to-service calls.

### Design Principles

- **Scope isolation is enforced at the API layer.** A user principal may only access their own user-memory (`/memory/users/{user_id}` where `user_id == principal.principal_id`). Org and project memory require membership scope. Admins may access all scopes.
- **All write operations are append-or-replace, never merge.** `PUT /memory/.../entries/{key}` fully replaces the entry.
- **`inject` metadata field controls context injection.** Entries with `metadata.inject = true` are automatically prepended to the agent's system context by `MindtraceAgentWorker` before execution. This is the mechanism for surfacing project config, org policies, and user preferences without tool calls.
- **Search endpoints are scope-local.** Searching `/memory/users/{user_id}/search` does not cross into project or org memory. Cross-scope search must be done with multiple requests or via a tool that fans out.
- **Session memory TTL is non-configurable per-entry via the API** (use the tool interface for per-entry TTL overrides). The API always writes with the store's `default_ttl`.

### Request / Response Models

```python
class MemoryEntryRequest(BaseModel):
    key: str
    value: str
    metadata: dict[str, Any] = {}    # set metadata.inject = True for context injection

class MemoryEntry(BaseModel):
    key: str
    value: str
    metadata: dict[str, Any]
    namespace: str
    created_at: datetime
    updated_at: datetime

class MemorySearchRequest(BaseModel):
    q: str
    top_k: int = 5

class SessionInfo(BaseModel):
    session_id: str
    user_id: str | None
    message_count: int
    last_active: datetime | None
    ttl_seconds: int | None
```

### Authorization Scopes (memory-specific)

The following scopes are added to the scope table in Section 7:

| Scope | Required for |
|---|---|
| `memory:read` | `GET` on user-scoped memory endpoints (own user only unless admin) |
| `memory:write` | `POST`, `PUT`, `DELETE` on user-scoped memory endpoints |
| `project:member` | `GET`, `POST`, `PUT` on project-scoped memory endpoints |
| `project:admin` | `DELETE` on project-scoped memory endpoints |
| `org:member` | `GET`, `POST` on org-scoped memory endpoints |
| `org:admin` | `PUT`, `DELETE` on org-scoped memory endpoints |

Session memory uses `tasks:read` / `tasks:submit` / `tasks:cancel` (existing scopes) — session memory is considered part of the task lifecycle, not standalone memory management.

### Context Injection Flow

When `MindtraceAgentWorker._run_agent()` starts executing a task, it performs the following injection sequence before calling `agent.run()`:

```
1. Load session history  (RedisHistoryStrategy.load(session_id))
2. Load session memory   (RedisMemoryStore.list_keys() + get() for inject=true entries)
3. Load user memory      (MongoMemoryStore(namespace="user:{user_id}").search(inject=true, top_k=10))
4. Load project memory   (MongoMemoryStore(namespace="project:{project_id}").search(inject=true, top_k=10))
   — only if run_context.project_id is set
5. Load org memory       (MongoMemoryStore(namespace="org:{org_id}").search(inject=true, top_k=5))
   — only if run_context.org_id is set
```

Injected entries are serialised as a structured block appended to the agent's `system_prompt`:

```
--- Context from memory ---
[user] preferred_language = Python
[project] camera_count = 6
[project] defect_classes = ["scratch", "dent", "discolouration"]
[org] compliance_standard = ISO-9001
--------------------------
```

This block is generated by a new helper `MemoryContextBuilder` in `agents/distributed/memory_api.py`. It is always placed after the agent's own system prompt, never replacing it. The total injected block is capped at 2 000 tokens; entries beyond the cap are silently dropped (lowest-priority scopes first).

### Implementation Notes

- `memory_api.py` is a thin HTTP layer. All storage logic lives in `RedisMemoryStore` / `MongoMemoryStore`.
- Session memory endpoints proxy to `RedisMemoryStore(namespace="session:{session_id}")`.
- User / project / org memory endpoints proxy to `MongoMemoryStore(namespace="{scope}:{id}")`.
- The `GET /sessions?user_id={user_id}` endpoint scans Redis keys matching `{key_prefix}:{user_id}:*` — this requires a Redis SCAN and is O(N); cache the result with a short TTL (30 s) per user.
- `MongoMemoryStore` requires `namespace` as a required constructor argument. The abstract base `AbstractMemoryStore` is updated to include `namespace: str` in its `__init__` signature so all implementations are consistent.

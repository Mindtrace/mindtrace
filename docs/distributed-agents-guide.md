# Mindtrace Distributed Agents — Developer Guide

**Version:** 1.2 | **Package:** `mindtrace-agents`

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Installation](#2-installation)
3. [Scenarios](#3-scenarios)
   - [Scenario 1 — Local Single-Process Agent](#scenario-1--local-single-process-agent)
   - [Scenario 2 — Agent with Persistent Redis Memory](#scenario-2--agent-with-persistent-redis-memory)
   - [Scenario 3 — Single Remote Agent via WebSocket](#scenario-3--single-remote-agent-via-websocket)
   - [Scenario 4 — Multi-Turn Conversation with session_id](#scenario-4--multi-turn-conversation-with-session_id)
   - [Scenario 5 — Building and Publishing a Skill Plugin](#scenario-5--building-and-publishing-a-skill-plugin)
   - [Scenario 6 — Observability: Querying Spans and Metrics](#scenario-6--observability-querying-spans-and-metrics)
4. [API Reference](#4-api-reference)
5. [Authentication Guide](#5-authentication-guide)
6. [Memory Architecture](#6-memory-architecture)
7. [Error Handling and Retries](#7-error-handling-and-retries)
8. [Deployment Checklist](#8-deployment-checklist)

---

## 1. Introduction

`mindtrace-agents` is a Python library for building and running AI agents that can execute locally in a single process or scale out across a fleet of remote machines. The library is designed so that the same agent code runs without modification whether it is invoked locally for development or dispatched to a remote worker in production.

The supported distributed topology is:

```
User (Machine A)  →  MindtraceAgentGateway (Machine B)  →  MindtraceAgentWorker (Machine C+)
```

A client connects to the `MindtraceAgentGateway` over WebSocket or HTTP. The gateway authenticates the request, publishes a task to a RabbitMQ queue, and relays streaming token events back to the client in real time as workers process them. Workers are stateless — session history and memory are stored in shared Redis and MongoDB, so any available worker can pick up any task without session affinity. This design lets you scale workers horizontally by adding machines without changing any gateway or client configuration.

The library introduces no new packages. All distributed components are optional submodules inside `mindtrace-agents`, enabled by installation extras. A basic `pip install mindtrace-agents` installs only the core agent runtime (OpenAI, Pydantic, mindtrace-core) and is suitable for local development.

---

## 2. Installation

Choose the install path that matches your deployment:

```bash
# Local development — no external infrastructure required
pip install mindtrace-agents

# Add persistent Redis-backed conversation history and session memory
pip install "mindtrace-agents[memory-redis]"

# Full distributed deployment: RabbitMQ queue, Redis, MongoDB, cluster runtime
pip install "mindtrace-agents[distributed]"
```

The `[distributed]` extra is a convenience bundle that installs all four sub-extras:

| Extra | What it enables |
|---|---|
| `mindtrace-agents[memory-redis]` | `RedisHistoryStrategy`, `RedisMemoryStore`, `RedisAgentTaskQueue` |
| `mindtrace-agents[memory-mongo]` | `MongoMemoryStore` with optional vector search |
| `mindtrace-agents[distributed-rabbitmq]` | `RabbitMQAgentTaskQueue` |
| `mindtrace-agents[distributed-cluster]` | `MindtraceAgentGateway`, `MindtraceAgentWorker`, `MindtraceAgentNode`, `MindtraceAgentRegistry`, `AgentObservabilityCollector` |

> **Note:** Attempting to import a class from a submodule whose extra is not installed raises an `ImportError` with a message that names the missing extra.

---

## 3. Scenarios

### Scenario 1 — Local Single-Process Agent

You want to define an agent and run it locally without any external infrastructure. This is the right starting point for developing and testing agent logic before connecting it to a distributed deployment.

```python
# local_agent.py
import asyncio
from mindtrace.agents import MindtraceAgent
from mindtrace.agents.tools import RunContext, Tool
from mindtrace.agents.execution.local import LocalTaskQueue
from mindtrace.agents.execution._queue import AgentTask
from mindtrace.agents.models.openai_chat import OpenAIChatModel


# --- Define tools -----------------------------------------------------------

async def get_weather(ctx: RunContext, city: str) -> str:
    """Return current weather for a city."""
    # Replace with a real API call in production.
    return f"The weather in {city} is sunny and 22°C."


async def convert_currency(ctx: RunContext, amount: float, from_currency: str, to_currency: str) -> str:
    """Convert an amount between two currency codes."""
    # Stub implementation.
    rate = 1.08 if (from_currency, to_currency) == ("USD", "EUR") else 1.0
    converted = amount * rate
    return f"{amount} {from_currency} = {converted:.2f} {to_currency}"


# --- Define the agent -------------------------------------------------------

class TravelAssistant(MindtraceAgent):
    def __init__(self) -> None:
        super().__init__(
            model=OpenAIChatModel(model_id="gpt-4o-mini"),
            name="travel_assistant",
            description="Answers travel-related questions about weather and currency.",
            system_prompt=(
                "You are a helpful travel assistant. "
                "Use the available tools to answer questions accurately."
            ),
            tools=[Tool(get_weather), Tool(convert_currency)],
        )


# --- Run it locally ---------------------------------------------------------

async def main() -> None:
    agent = TravelAssistant()

    queue = LocalTaskQueue()
    queue.register(agent)

    task = AgentTask(
        agent_name="travel_assistant",
        input="What is the weather in Paris and how much is 100 USD in EUR?",
    )
    task_id = await queue.submit(task)
    result = await queue.get_result(task_id)
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
```

You can also call the agent directly without a queue:

```python
async def main() -> None:
    agent = TravelAssistant()
    result = await agent.run("What is the weather in Tokyo?")
    print(result)
```

> **What this demonstrated:**
> `MindtraceAgent` is the concrete agent class. Tools are plain async functions decorated with `Tool`. `LocalTaskQueue` is the in-process queue for local use — it requires no Redis or RabbitMQ. You can call `agent.run()` directly for one-off invocations, or use the queue API for task-based orchestration.

---

### Scenario 2 — Agent with Persistent Redis Memory

You want conversation history to survive process restarts so that a user picking up a session tomorrow gets the same context they had yesterday. You also want tools to read and write key-value memory scoped to the current session.

**Requires:** `pip install "mindtrace-agents[memory-redis]"`

```python
# redis_memory_agent.py
import asyncio
from dataclasses import dataclass

from mindtrace.agents import MindtraceAgent
from mindtrace.agents.tools import RunContext, Tool
from mindtrace.agents.history.redis import RedisHistoryStrategy
from mindtrace.agents.memory.redis import RedisMemoryStore
from mindtrace.agents.models.openai_chat import OpenAIChatModel

REDIS_URL = "redis://localhost:6379"
SESSION_ID = "user-42-session-001"


# --- Deps carries the memory store into tools --------------------------------

@dataclass
class SessionDeps:
    memory: RedisMemoryStore


# --- Tools that read/write session memory ------------------------------------

async def remember_preference(ctx: RunContext[SessionDeps], key: str, value: str) -> str:
    """Store a user preference in session memory."""
    await ctx.deps.memory.save(key=key, value=value)
    return f"Remembered: {key} = {value}"


async def recall_preference(ctx: RunContext[SessionDeps], key: str) -> str:
    """Retrieve a previously stored user preference."""
    entry = await ctx.deps.memory.get(key)
    if entry is None:
        return f"No memory found for key: {key}"
    return f"{key} = {entry.value}"


# --- Agent definition --------------------------------------------------------

class PersonalAssistant(MindtraceAgent):
    def __init__(self, history: RedisHistoryStrategy) -> None:
        super().__init__(
            model=OpenAIChatModel(model_id="gpt-4o-mini"),
            name="personal_assistant",
            description="A personal assistant that remembers user preferences.",
            system_prompt=(
                "You are a personal assistant. "
                "When a user tells you a preference, store it with remember_preference. "
                "When asked about a preference, use recall_preference."
            ),
            tools=[Tool(remember_preference), Tool(recall_preference)],
            deps_type=SessionDeps,
            history=history,
        )


# --- Wire up Redis history and session memory --------------------------------

async def main() -> None:
    history = RedisHistoryStrategy(
        redis_url=REDIS_URL,
        ttl=86400,           # history keys expire after 24 hours
        key_prefix="myapp:history",
    )

    session_memory = RedisMemoryStore(
        redis_url=REDIS_URL,
        namespace=f"session:{SESSION_ID}",
        default_ttl=3600,    # session memory expires after 1 hour
    )

    agent = PersonalAssistant(history=history)
    deps = SessionDeps(memory=session_memory)

    # First turn — agent stores the preference in Redis
    response1 = await agent.run(
        "My favourite city is Kyoto. Remember that.",
        deps=deps,
        session_id=SESSION_ID,
    )
    print("Turn 1:", response1)

    # Second turn — agent recalls from Redis history (not in-process state)
    response2 = await agent.run(
        "What is my favourite city?",
        deps=deps,
        session_id=SESSION_ID,
    )
    print("Turn 2:", response2)

    # Restart the process and run again — history is loaded from Redis
    response3 = await agent.run(
        "Remind me what you know about my travel preferences.",
        deps=deps,
        session_id=SESSION_ID,
    )
    print("Turn 3 (after simulated restart):", response3)


if __name__ == "__main__":
    asyncio.run(main())
```

> **What this demonstrated:**
> `RedisHistoryStrategy` persists conversation messages per `session_id`. Pass the same `session_id` across runs and the agent picks up where it left off. `RedisMemoryStore` provides a key-value store namespaced to the session, accessible from within tools via `ctx.deps`. Both stores are shared — any machine that holds the `session_id` can resume the session without affinity to a specific worker.

---

### Scenario 3 — Single Remote Agent via WebSocket

You want to deploy your agent to a remote machine, invoke it from a client machine, and receive token-by-token streaming responses. This is the core distributed use case.

**Requires:** `pip install "mindtrace-agents[distributed]"`

**Infrastructure needed:** Redis, RabbitMQ

#### Step 1 — Register the agent definition (run once, on any machine)

Before the gateway or workers start, register the agent in the shared registry. This is an admin operation, typically run once during deployment.

```python
# register_agent.py  (run on Machine B or in a deploy script)
import asyncio
from mindtrace.agents.distributed.registry import MindtraceAgentRegistry, AgentDefinition

REDIS_URL = "redis://redis:6379"

async def main() -> None:
    registry = MindtraceAgentRegistry(redis_url=REDIS_URL, heartbeat_ttl=30)

    definition = AgentDefinition(
        name="travel_assistant",
        description="Answers weather and currency questions.",
        agent_class="myapp.agents:TravelAssistant",   # allowlisted dotted path
        init_kwargs={},                                # passed to TravelAssistant()
        required_skills=[],
        required_provider=None,
    )
    await registry.register_agent(definition)
    print("Agent registered.")

asyncio.run(main())
```

> **Note:** `agent_class` must be added to the allowlist before registration is accepted. Run:
> ```bash
> mindtrace agents allowlist-add --path "myapp.agents:TravelAssistant" --type agent_class
> ```

#### Step 2 — Start the gateway (Machine B)

```python
# gateway_server.py  (Machine B)
import asyncio
from mindtrace.agents.distributed.gateway import MindtraceAgentGateway
from mindtrace.agents.distributed.registry import MindtraceAgentRegistry
from mindtrace.agents.execution.rabbitmq import RabbitMQAgentTaskQueue

REDIS_URL = "redis://redis:6379"
RABBITMQ_URL = "amqp://guest:guest@rabbitmq:5672/"

async def main() -> None:
    registry = MindtraceAgentRegistry(redis_url=REDIS_URL)

    task_queue = RabbitMQAgentTaskQueue(
        rabbitmq_url=RABBITMQ_URL,
        redis_url=REDIS_URL,
        queue_name="mindtrace.agent.tasks",
        max_retries=3,
    )

    gateway = MindtraceAgentGateway(
        registry=registry,
        task_queue=task_queue,
        collector_url="http://collector:8001",
        auth_secret=None,          # set MINDTRACE_JWKS_URL env var for JWT validation
        host="0.0.0.0",
        port=8000,
    )
    await gateway.start()

asyncio.run(main())
```

#### Step 3 — Start the worker (Machine C)

```python
# worker_server.py  (Machine C)
import asyncio
from mindtrace.agents.distributed.worker import MindtraceAgentWorker
from mindtrace.agents.distributed.registry import MindtraceAgentRegistry

REDIS_URL = "redis://redis:6379"

async def main() -> None:
    registry = MindtraceAgentRegistry(redis_url=REDIS_URL)

    worker = MindtraceAgentWorker(
        agent_registry=registry,
        redis_pubsub_url=REDIS_URL,
        collector_url="http://collector:8001",
    )
    await worker.start()

asyncio.run(main())
```

#### Step 4 — Connect and invoke from the client (Machine A)

```python
# client.py  (Machine A)
import asyncio
import json
import websockets

GATEWAY_URL = "ws://gateway:8000/ws/agents"
TOKEN = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9..."   # JWT from your identity provider


async def main() -> None:
    headers = {"Authorization": f"Bearer {TOKEN}"}

    async with websockets.connect(GATEWAY_URL, additional_headers=headers) as ws:
        # The gateway sends a connection message immediately
        connect_msg = json.loads(await ws.recv())
        assert connect_msg["type"] == "connected"
        session_id = connect_msg["session_id"]
        print(f"Connected. session_id={session_id}")

        # Send an invocation request
        request = {
            "agent_name": "travel_assistant",
            "input": "What is the weather in Barcelona and how much is 200 USD in EUR?",
            "session_id": session_id,
            "stream": True,
        }
        await ws.send(json.dumps(request))

        # The gateway acknowledges immediately with a task_id
        ack = json.loads(await ws.recv())
        assert ack["type"] == "ack"
        print(f"Task acknowledged. task_id={ack['task_id']}")

        # Stream token events until we receive the final response
        async for raw in ws:
            msg = json.loads(raw)

            if msg["type"] == "stream_event":
                if msg["event_kind"] == "part_delta":
                    print(msg["payload"].get("delta", ""), end="", flush=True)

            elif msg["type"] == "response":
                print()   # newline after streamed tokens
                print(f"\nFinal output: {msg['output']}")
                print(f"Tokens used: {msg['usage']}")
                break

            elif msg["type"] == "error":
                print(f"Error [{msg['code']}]: {msg['message']}")
                break


asyncio.run(main())
```

#### REST fallback (no streaming)

If you do not need streaming, use the REST endpoint:

```python
import httpx

response = httpx.post(
    "http://gateway:8000/agents/travel_assistant/invoke",
    json={"agent_name": "travel_assistant", "input": "Weather in Lisbon?", "stream": False},
    headers={"Authorization": f"Bearer {TOKEN}"},
    timeout=120,
)
result = response.json()
print(result["output"])
```

> **What this demonstrated:**
> The gateway authenticates the WebSocket connection, enqueues the task to RabbitMQ, and relays `AgentStreamEvent` frames as the worker produces tokens. The worker loads the agent from the registry by name, executes it, and publishes each `NativeEvent` to a per-task Redis Pub/Sub channel that the gateway subscribes to. The final `AgentInvokeResponse` arrives after the agent run completes.

---

### Scenario 4 — Multi-Turn Conversation with session_id

You want to support a chatbot-style interaction where the user sends several messages and each message builds on previous ones. The key is to reuse the `session_id` returned in `AgentSessionMessage` across every request.

```python
# multi_turn_client.py
import asyncio
import json
import websockets

GATEWAY_URL = "ws://gateway:8000/ws/agents"
TOKEN = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9..."


async def invoke(ws: websockets.WebSocketClientProtocol, session_id: str, user_input: str) -> str:
    """Send one message and collect the full response text."""
    await ws.send(json.dumps({
        "agent_name": "travel_assistant",
        "input": user_input,
        "session_id": session_id,   # reuse the same session across turns
        "stream": True,
    }))

    # Discard the ack
    ack = json.loads(await ws.recv())
    assert ack["type"] == "ack"

    output_parts: list[str] = []
    async for raw in ws:
        msg = json.loads(raw)
        if msg["type"] == "stream_event" and msg["event_kind"] == "part_delta":
            output_parts.append(msg["payload"].get("delta", ""))
        elif msg["type"] == "response":
            return msg["output"]
        elif msg["type"] == "error":
            raise RuntimeError(f"Agent error [{msg['code']}]: {msg['message']}")

    return "".join(output_parts)


async def main() -> None:
    headers = {"Authorization": f"Bearer {TOKEN}"}

    async with websockets.connect(GATEWAY_URL, additional_headers=headers) as ws:
        # Capture the session_id from the connection message
        connect_msg = json.loads(await ws.recv())
        session_id = connect_msg["session_id"]
        print(f"Session started: {session_id}\n")

        # Turn 1 — provide context
        turn1 = await invoke(ws, session_id, "I am planning a trip to Japan next month.")
        print(f"Assistant: {turn1}\n")

        # Turn 2 — follow-up that requires memory of turn 1
        turn2 = await invoke(ws, session_id, "What currency should I bring?")
        print(f"Assistant: {turn2}\n")

        # Turn 3 — another follow-up
        turn3 = await invoke(ws, session_id, "And what is the weather like there in May?")
        print(f"Assistant: {turn3}\n")

        print(f"All three turns used session_id={session_id}")


asyncio.run(main())
```

**Resuming a session from a new WebSocket connection**

If the WebSocket connection drops and the user reconnects, pass the `session_id` you captured earlier. The gateway and worker do not need to be the same instances — session history is stored in Redis.

```python
async with websockets.connect(GATEWAY_URL, additional_headers=headers) as ws:
    connect_msg = json.loads(await ws.recv())
    # Override the session_id with the one from the previous connection
    session_id = "the-session-id-from-the-previous-connection"

    turn4 = await invoke(ws, session_id, "Where were we? Remind me what trip we discussed.")
    print(f"Assistant: {turn4}")
```

> **What this demonstrated:**
> Passing the same `session_id` in every `AgentInvokeRequest` causes the worker to load the conversation history from Redis before each run. The session persists across WebSocket reconnections, process restarts, and worker replacements because all state is stored in shared Redis, not in any single process.

---

### Scenario 5 — Building and Publishing a Skill Plugin

You have a web-search capability that several agents need. You want to package it once, publish it to PyPI, and have it automatically available in any Mindtrace worker that installs it — without modifying the worker code.

#### Step 1 — Implement the skill

```python
# my_search_skill/skills.py
from __future__ import annotations

import httpx
from mindtrace.agents.plugins.skill import AbstractSkill
from mindtrace.agents.tools import RunContext, Tool
from mindtrace.agents.toolsets._toolset import AbstractToolset


class WebSearchSkill(AbstractSkill):
    """Provides web search capability to any agent that declares it as required."""

    @property
    def skill_name(self) -> str:
        return "web_search"

    @property
    def skill_version(self) -> str:
        return "1.0.0"

    @property
    def skill_description(self) -> str:
        return "Search the web and return a list of results."

    async def setup(self) -> None:
        """Called once by MindtracePluginRegistry after discovery."""
        self._client = httpx.AsyncClient(timeout=10.0)

    async def teardown(self) -> None:
        """Called on worker shutdown."""
        await self._client.aclose()

    # Tools defined as methods are automatically registered on AbstractToolset
    async def search(self, ctx: RunContext, query: str, max_results: int = 5) -> str:
        """Search the web for the given query. Returns a summary of top results."""
        # Replace with your actual search API call.
        response = await self._client.get(
            "https://api.search.example.com/search",
            params={"q": query, "count": max_results},
        )
        data = response.json()
        results = [f"- {r['title']}: {r['url']}" for r in data.get("results", [])]
        return "\n".join(results) if results else "No results found."
```

#### Step 2 — Register the entry point in pyproject.toml

```toml
# my_search_skill/pyproject.toml
[project]
name = "my-search-skill"
version = "1.0.0"
dependencies = ["mindtrace-agents", "httpx>=0.27"]

[project.entry-points."mindtrace.skills"]
web_search = "my_search_skill.skills:WebSearchSkill"
```

#### Step 3 — Declare the skill requirement in the agent definition

When registering the agent, list the skill name in `required_skills`:

```python
from mindtrace.agents.distributed.registry import MindtraceAgentRegistry, AgentDefinition

async def register() -> None:
    registry = MindtraceAgentRegistry(redis_url="redis://redis:6379")
    await registry.register_agent(AgentDefinition(
        name="research_agent",
        description="Researches topics using web search.",
        agent_class="myapp.agents:ResearchAgent",
        required_skills=["web_search"],   # must match WebSearchSkill.skill_name
    ))
```

#### Step 4 — Install and verify on the worker machine

```bash
# On the worker machine:
pip install my-search-skill
```

On the next worker startup, `MindtracePluginRegistry.discover()` finds the entry point, instantiates `WebSearchSkill`, calls `setup()`, and makes it available. The worker's `_load_agent()` method then injects it as a `CompoundToolset` when instantiating `ResearchAgent`.

You can verify discovery at runtime:

```python
from mindtrace.agents.plugins.registry import MindtracePluginRegistry

plugin_registry = MindtracePluginRegistry()
plugin_registry.discover()

for skill_info in plugin_registry.list_skills():
    print(f"{skill_info.name} v{skill_info.version}: {skill_info.description}")
```

> **What this demonstrated:**
> `AbstractSkill` extends `AbstractToolset`, so skills are drop-in toolsets with no agent-side changes. Skills are discovered from Python entry-points at worker startup — no registry call or code change is needed on the worker. `setup()` and `teardown()` handle async resource lifecycle (HTTP clients, database connections). Installing the skill package is the only deployment step.

---

### Scenario 6 — Observability: Querying Spans and Metrics

You want to understand how your agents are performing in production: which tool calls are slow, what the error rate is, and how many tokens you are consuming.

**Requires:** `pip install "mindtrace-agents[distributed]"`

#### Start the observability collector

```python
# collector_server.py
import asyncio
from mindtrace.agents.distributed.collector import AgentObservabilityCollector

async def main() -> None:
    collector = AgentObservabilityCollector(
        otlp_endpoint="http://jaeger:4318",       # export to Jaeger or Grafana Tempo
        mongo_url="mongodb://mongo:27017",         # persist spans for historical queries
        host="0.0.0.0",
        port=8001,
    )
    await collector.start()

asyncio.run(main())
```

#### Query spans and metrics from a client

```python
# observability_client.py
import asyncio
from datetime import datetime, timedelta
from mindtrace.agents.distributed.collector import AgentObservabilityCollector, SpanQuery

async def main() -> None:
    collector = AgentObservabilityCollector(
        mongo_url="mongodb://mongo:27017",
        host="0.0.0.0",
        port=8001,
    )

    # Query all spans for "travel_assistant" in the last hour
    query = SpanQuery(
        agent_name="travel_assistant",
        from_time=datetime.utcnow() - timedelta(hours=1),
        to_time=datetime.utcnow(),
        status="ok",
        limit=50,
    )
    spans = await collector.query_spans(query)
    for span in spans:
        print(
            f"span_id={span.span_id} "
            f"session={span.session_id} "
            f"duration={span.duration_ms:.0f}ms "
            f"tokens={span.input_tokens}+{span.output_tokens}"
        )

    # Get aggregate metrics
    metrics = await collector.agent_metrics("travel_assistant")
    print(f"\n--- travel_assistant metrics ---")
    print(f"Total runs:    {metrics.total_runs}")
    print(f"Error rate:    {metrics.error_rate:.1%}")
    print(f"p50 latency:   {metrics.latency_p50_ms:.0f}ms")
    print(f"p95 latency:   {metrics.latency_p95_ms:.0f}ms")
    print(f"p99 latency:   {metrics.latency_p99_ms:.0f}ms")
    print(f"Input tokens:  {metrics.total_input_tokens:,}")
    print(f"Output tokens: {metrics.total_output_tokens:,}")
    print(f"Tool calls:    {metrics.tool_call_counts}")


asyncio.run(main())
```

#### Check service health

Every Mindtrace distributed service exposes `GET /health`:

```python
import httpx

health = httpx.get("http://gateway:8000/health").json()
print(f"Gateway status: {health['status']}")
for component in health["components"]:
    print(f"  {component['name']}: {component['status']} ({component.get('latency_ms', '?')}ms)")
```

#### Trace context in Jaeger or Grafana Tempo

When `otlp_endpoint` is configured on the collector, every `AgentSpan` is exported in OTLP JSON format. The `trace_id` in `AgentInvokeResponse` is a W3C traceparent trace ID — paste it into your Jaeger or Grafana Tempo UI to see the full distributed trace, from gateway through worker to each tool call.

> **What this demonstrated:**
> `AgentObservabilityCollector` is a standalone service that ingests spans from workers, stores them in MongoDB, exports them to an OTLP endpoint, and exposes a query API. `SpanQuery` lets you filter by agent name, session, time range, or status. `AgentMetrics` gives you aggregate latency percentiles, error rates, and token counts. The `GET /health` endpoint on every service component lets load balancers and Kubernetes probes check readiness without credentials.

---

## 4. API Reference

### `MindtraceAgentGateway`

WebSocket and REST entry point for distributed agent execution. Authenticates clients, enqueues tasks to RabbitMQ, and relays streaming `NativeEvent` frames from Redis Pub/Sub back to connected WebSocket clients.

**Requires:** `mindtrace-agents[distributed-cluster]`

```python
from mindtrace.agents.distributed.gateway import MindtraceAgentGateway
```

**Constructor**

```python
MindtraceAgentGateway(
    registry: MindtraceAgentRegistry,
    task_queue: AbstractTaskQueue,
    collector_url: str | None = None,
    auth_secret: str | None = None,
    **kwargs: Any,
) -> None
```

| Parameter | Type | Description |
|---|---|---|
| `registry` | `MindtraceAgentRegistry` | Registry used to look up `AgentDefinition` and validate agent names before enqueuing. |
| `task_queue` | `AbstractTaskQueue` | Queue used to publish `AgentTaskEnvelope` messages. Typically `RabbitMQAgentTaskQueue` in production. |
| `collector_url` | `str \| None` | Base URL of the `AgentObservabilityCollector`. If `None`, spans are not forwarded. |
| `auth_secret` | `str \| None` | Deprecated parameter reserved for future HMAC pre-shared-key auth. Use `MINDTRACE_JWKS_URL` env var for JWT validation instead. |
| `**kwargs` | `Any` | Forwarded to the parent `Gateway` class (e.g., `host`, `port`, `max_concurrent_sessions`). |

**Key methods**

```python
async def websocket_endpoint(self, websocket: WebSocket) -> None
```
WebSocket handler registered at `/ws/agents`. Authenticates the connection, assigns a `session_id`, and manages the full task lifecycle: receive `AgentInvokeRequest`, publish to queue, relay `AgentStreamEvent` frames, send final `AgentInvokeResponse`.

```python
async def invoke_agent(self, name: str, request: AgentInvokeRequest) -> AgentInvokeResponse
```
REST handler at `POST /agents/{name}/invoke`. Blocks until the agent run completes; does not stream. Returns the full `AgentInvokeResponse`.

```python
async def get_task_status(self, task_id: str) -> TaskStatusResponse
```
REST handler at `GET /agents/{name}/tasks/{task_id}`. Returns the current status of a queued or completed task.

```python
async def list_agents(self) -> list[AgentInfo]
```
REST handler at `GET /agents/`. Returns all `AgentDefinition` entries from the registry.

**Raises**
- `AuthenticationError`: on WebSocket connect if the bearer token or API key is missing, expired, or has an invalid signature.
- `AuthorizationError`: if the authenticated principal lacks the required scope for the requested operation.
- `CircuitOpenError`: if the task queue circuit-breaker is open; the gateway sends an `AgentErrorMessage` with `code="service_unavailable"` instead of raising to the client.

**Example**

```python
gateway = MindtraceAgentGateway(
    registry=registry,
    task_queue=RabbitMQAgentTaskQueue(
        rabbitmq_url="amqp://localhost/",
        redis_url="redis://localhost:6379",
    ),
    collector_url="http://collector:8001",
    host="0.0.0.0",
    port=8000,
)
await gateway.start()
```

---

### `MindtraceAgentWorker`

Consumes `AgentTaskEnvelope` messages from the queue, loads agents from the registry, executes them, and publishes `NativeEvent` frames to Redis Pub/Sub for gateway relay.

**Requires:** `mindtrace-agents[distributed-cluster]`

```python
from mindtrace.agents.distributed.worker import MindtraceAgentWorker
```

**Constructor**

```python
MindtraceAgentWorker(
    agent_registry: MindtraceAgentRegistry,
    plugin_registry: MindtracePluginRegistry | None = None,
    collector_url: str | None = None,
    redis_pubsub_url: str | None = None,
    **kwargs: Any,
) -> None
```

| Parameter | Type | Description |
|---|---|---|
| `agent_registry` | `MindtraceAgentRegistry` | Registry from which agent definitions are loaded by name. |
| `plugin_registry` | `MindtracePluginRegistry \| None` | If provided, skills and model providers discovered by this registry are injected into agents at load time. |
| `collector_url` | `str \| None` | URL of `AgentObservabilityCollector`. Spans are POSTed here after each run. |
| `redis_pubsub_url` | `str \| None` | Redis URL used for Pub/Sub publishing of `NativeEvent` frames. |
| `**kwargs` | `Any` | Forwarded to the parent `Worker` class (e.g., `max_concurrent_agents`). |

**Notes**

- Workers check the `MindtraceAllowlistRegistry` before importing any agent class or deserializing any deps type. An `AllowlistViolationError` routes the task to the DLQ without retrying.
- Workers respect `AgentTaskEnvelope.task_ttl_seconds`: if the task has aged past its deadline by the time the worker picks it up, the envelope is sent to the DLQ immediately without executing.
- Workers limit concurrency with an internal semaphore (`max_concurrent_agents`, default: 4). When all slots are occupied the worker stops consuming from the queue rather than NACKing messages.

**Example**

```python
worker = MindtraceAgentWorker(
    agent_registry=MindtraceAgentRegistry(redis_url="redis://redis:6379"),
    plugin_registry=plugin_registry,
    redis_pubsub_url="redis://redis:6379",
    collector_url="http://collector:8001",
)
await worker.start()
```

---

### `MindtraceAgentNode`

Launches `MindtraceAgentWorker` subprocesses and registers them with `MindtraceAgentRegistry` on startup. Use this when you want a single host process to manage multiple worker subprocesses.

**Requires:** `mindtrace-agents[distributed-cluster]`

```python
from mindtrace.agents.distributed.node import MindtraceAgentNode
```

**Constructor**

```python
MindtraceAgentNode(
    agent_registry_url: str,
    worker_class: type[MindtraceAgentWorker] = MindtraceAgentWorker,
    plugin_registry: MindtracePluginRegistry | None = None,
    **kwargs: Any,
) -> None
```

| Parameter | Type | Description |
|---|---|---|
| `agent_registry_url` | `str` | HTTP URL of the `MindtraceAgentRegistry` service. Workers launched by this node register themselves here. |
| `worker_class` | `type[MindtraceAgentWorker]` | The worker class to instantiate. Subclass `MindtraceAgentWorker` if you need custom lifecycle hooks. |
| `plugin_registry` | `MindtracePluginRegistry \| None` | Passed through to each launched worker. |

**Key methods**

```python
async def launch_worker(self, payload: LaunchWorkerInput) -> LaunchWorkerOutput
```
Extends the base `Node.launch_worker()` to register the new worker in the agent registry immediately after launch.

---

### `MindtraceAgentRegistry` and `AgentDefinition`

Redis-backed registry for agent definitions and live worker locations. Agents are registered by an admin at deploy time; workers register and heartbeat themselves at runtime.

**Requires:** `mindtrace-agents[distributed-cluster]`

```python
from mindtrace.agents.distributed.registry import MindtraceAgentRegistry, AgentDefinition
```

**`AgentDefinition`**

```python
class AgentDefinition(BaseModel):
    name: str
    description: str | None = None
    agent_class: str           # allowlisted dotted path, e.g. "myapp.agents:MyAgent"
    init_kwargs: dict[str, Any] = {}
    required_skills: list[str] = []
    required_provider: str | None = None
```

| Field | Description |
|---|---|
| `name` | Unique identifier used in `AgentInvokeRequest.agent_name` and registry lookups. |
| `agent_class` | Dotted import path to the agent class. Must be pre-registered in `MindtraceAllowlistRegistry`. |
| `init_kwargs` | Keyword arguments passed verbatim to the agent class constructor on the worker. |
| `required_skills` | Skill names (matching `AbstractSkill.skill_name`) that must be discovered by the worker's plugin registry before the agent is instantiated. |
| `required_provider` | Model provider name that must be available in the plugin registry. |

**`MindtraceAgentRegistry` Constructor**

```python
MindtraceAgentRegistry(
    redis_url: str,
    heartbeat_ttl: int = 30,
    **kwargs: Any,
) -> None
```

| Parameter | Description |
|---|---|
| `redis_url` | Redis connection URL. All definitions and worker registrations are persisted here. |
| `heartbeat_ttl` | Seconds before a worker is considered stale if no heartbeat is received. Workers are evicted after 3 missed intervals. |

**Key methods**

```python
async def register_agent(self, definition: AgentDefinition) -> None
```
Persist an `AgentDefinition`. Raises `HTTP 422` (at the API layer) if `definition.agent_class` is not in the allowlist.

```python
async def get_agent_definition(self, agent_name: str) -> AgentDefinition | None
```
Return the definition for `agent_name`, or `None` if it is not registered.

```python
async def list_agents(self) -> list[AgentDefinition]
```
Return all registered agent definitions.

```python
async def register_worker(
    self,
    worker_id: str,
    agent_names: list[str],
    url: str,
    node_id: str,
) -> None
```
Register a live worker. Called automatically by workers on startup.

```python
async def heartbeat(self, worker_id: str) -> None
```
Refresh the TTL on a worker's registry entry. Workers call this on a background thread.

```python
async def find_workers(self, agent_name: str) -> list[WorkerInfo]
```
Return all live workers that have registered as capable of running `agent_name`.

```python
async def deregister_worker(self, worker_id: str) -> None
```
Remove a worker from the registry. Called automatically on clean shutdown.

**Example**

```python
registry = MindtraceAgentRegistry(redis_url="redis://redis:6379", heartbeat_ttl=30)
await registry.register_agent(AgentDefinition(
    name="my_agent",
    agent_class="myapp.agents:MyAgent",
    required_skills=["web_search"],
))
workers = await registry.find_workers("my_agent")
```

---

### `RabbitMQAgentTaskQueue`

Publishes `AgentTaskEnvelope` messages to a RabbitMQ exchange. Results and streaming events are read from Redis. Failed tasks are routed to a dead-letter queue.

**Requires:** `mindtrace-agents[distributed-rabbitmq]`

```python
from mindtrace.agents.execution.rabbitmq import RabbitMQAgentTaskQueue
```

**Constructor**

```python
RabbitMQAgentTaskQueue(
    rabbitmq_url: str,
    redis_url: str,
    queue_name: str = "mindtrace.agent.tasks",
    dlq_name: str = "mindtrace.agent.tasks.dlq",
    result_ttl: int = 3600,
    max_retries: int = 3,
) -> None
```

**Key methods**

| Method | Description |
|---|---|
| `async submit(task: AgentTask) -> str` | Serialize and publish the task. Returns `task_id`. |
| `async get_result(task_id: str, timeout: int = 300) -> Any` | Poll the Redis result key with exponential backoff. Raises `TimeoutError` if the result does not arrive within `timeout` seconds. |
| `async cancel(task_id: str) -> None` | Write a cancellation flag to Redis. The worker checks this flag before beginning execution. |
| `async status(task_id: str) -> TaskStatus` | Read the task status key from Redis. |
| `async requeue_from_dlq(task_id: str) -> None` | Reset `retry_count` to 0 and re-publish the envelope from the DLQ to the main queue. Requires `dlq:manage` scope. |

---

### `RedisAgentTaskQueue`

Lightweight Redis list-based queue for smaller deployments that do not require RabbitMQ. Uses `LPUSH` for submission and `BRPOP` for worker consumption.

**Requires:** `mindtrace-agents[memory-redis]`

```python
from mindtrace.agents.execution.redis import RedisAgentTaskQueue
```

**Constructor**

```python
RedisAgentTaskQueue(
    redis_url: str,
    queue_name: str = "mindtrace:agent:tasks",
    result_ttl: int = 3600,
) -> None
```

**Key methods:** same interface as `RabbitMQAgentTaskQueue` (`submit`, `get_result`, `cancel`, `status`). Does not support `requeue_from_dlq`.

---

### `RedisHistoryStrategy`

Persists conversation messages to Redis, isolated per `session_id`. The TTL is refreshed on every `save()` call, keeping active sessions alive.

**Requires:** `mindtrace-agents[memory-redis]`

```python
from mindtrace.agents.history.redis import RedisHistoryStrategy
```

**Constructor**

```python
RedisHistoryStrategy(
    redis_url: str,
    ttl: int = 86400,
    key_prefix: str = "mindtrace:history",
    **kwargs: Any,
) -> None
```

| Parameter | Description |
|---|---|
| `redis_url` | Redis connection URL. |
| `ttl` | Seconds before a session's history key expires if no new messages are saved. Default: 24 hours. |
| `key_prefix` | Namespace prefix for all history keys. Keys follow the pattern `{key_prefix}:{session_id}`. |

**Key methods**

```python
async def load(self, session_id: str) -> list[ModelMessage]
async def save(self, session_id: str, messages: list[ModelMessage]) -> None
async def clear(self, session_id: str) -> None
```

**Example**

```python
history = RedisHistoryStrategy(redis_url="redis://localhost:6379", ttl=3600)
agent = MindtraceAgent(..., history=history)
result = await agent.run("Hello", session_id="sess-001")
```

---

### `RedisMemoryStore`

Short-term, TTL-scoped key-value memory backed by Redis hashes. Supports prefix-scan search. Use for per-task or per-session working memory.

**Requires:** `mindtrace-agents[memory-redis]`

```python
from mindtrace.agents.memory.redis import RedisMemoryStore
```

**Constructor**

```python
RedisMemoryStore(
    redis_url: str,
    namespace: str,
    default_ttl: int = 3600,
    **kwargs: Any,
) -> None
```

| Parameter | Description |
|---|---|
| `namespace` | Key namespace prefix, e.g. `"session:abc123"` or `"task:xyz"`. All keys in this store are prefixed `{namespace}:{key}`. |
| `default_ttl` | Default expiry in seconds for saved entries. |

**Key methods**

```python
async def save(self, key: str, value: str, metadata: dict | None = None, ttl: int | None = None) -> None
async def get(self, key: str) -> MemoryEntry | None
async def search(self, query: str, top_k: int = 5) -> list[MemoryEntry]  # prefix scan only
async def delete(self, key: str) -> None
async def list_keys(self) -> list[str]
```

> **Note:** `search()` on `RedisMemoryStore` performs a prefix scan, not semantic or vector search. For vector similarity search, use `MongoMemoryStore` with an `EmbeddingProvider`.

---

### `MongoMemoryStore`

Long-term, persistent memory backed by MongoDB. Supports full-text search via `$text` and vector similarity search when an `EmbeddingProvider` is configured.

**Requires:** `mindtrace-agents[memory-mongo]`

```python
from mindtrace.agents.memory.mongo import MongoMemoryStore
```

**Constructor**

```python
MongoMemoryStore(
    mongo_url: str,
    database: str,
    collection: str,
    namespace: str,
    embedding_provider: EmbeddingProvider | None = None,
    vector_index_name: str = "vector_index",
    **kwargs: Any,
) -> None
```

| Parameter | Description |
|---|---|
| `namespace` | Namespace tag applied to all documents, e.g. `"agent:my_agent:user:user123"`. Documents from different namespaces share a collection but are isolated by this field. |
| `embedding_provider` | Optional object implementing `async def embed(self, text: str) -> list[float]`. When provided, `search()` uses `$vectorSearch` aggregation. When absent, falls back to `$text` search. |
| `vector_index_name` | Name of the MongoDB Atlas Search vector index on this collection. |

**Key methods**

```python
async def save(self, key: str, value: str, metadata: dict | None = None) -> None
async def get(self, key: str) -> MemoryEntry | None
async def search(self, query: str, top_k: int = 5) -> list[MemoryEntry]
async def delete(self, key: str) -> None
async def list_keys(self) -> list[str]
```

**`EmbeddingProvider` protocol**

```python
class EmbeddingProvider(Protocol):
    async def embed(self, text: str) -> list[float]: ...
```

Implement this protocol to connect any embedding backend (OpenAI, Cohere, local sentence-transformers, etc.).

---

### `AgentObservabilityCollector`, `SpanQuery`, and `AgentMetrics`

Centralized span ingestion and metrics service. Workers POST spans here; this service exports to OTLP and exposes a query API.

**Requires:** `mindtrace-agents[distributed-cluster]`

```python
from mindtrace.agents.distributed.collector import (
    AgentObservabilityCollector,
    SpanQuery,
    AgentMetrics,
)
```

**`AgentObservabilityCollector` Constructor**

```python
AgentObservabilityCollector(
    otlp_endpoint: str | None = None,
    mongo_url: str | None = None,
    **kwargs: Any,
) -> None
```

| Parameter | Description |
|---|---|
| `otlp_endpoint` | OTLP HTTP endpoint, e.g. `"http://jaeger:4318"`. When set, every ingested span is exported in OTLP JSON format. |
| `mongo_url` | MongoDB connection URL for span persistence. When absent, spans are only held in memory and are lost on restart. |

**Key methods**

```python
async def ingest_span(self, span: AgentSpan) -> None
async def query_spans(self, query: SpanQuery) -> list[AgentSpan]
async def agent_metrics(self, agent_name: str) -> AgentMetrics
```

**`SpanQuery` fields**

```python
class SpanQuery(BaseModel):
    agent_name: str | None = None
    session_id: str | None = None
    trace_id: str | None = None
    from_time: datetime | None = None
    to_time: datetime | None = None
    status: Literal["ok", "error"] | None = None
    limit: int = 100
```

**`AgentMetrics` fields**

```python
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
```

---

### `AgentRunContext`

Serializable context object that carries W3C TraceContext identifiers, session and user IDs, and serialized deps across process and network boundaries.

```python
from mindtrace.agents.context.propagation import AgentRunContext
```

**Fields**

| Field | Type | Description |
|---|---|---|
| `trace_id` | `str` | W3C TraceContext trace-id (32 hex characters). |
| `span_id` | `str` | W3C TraceContext parent-id (16 hex characters). |
| `session_id` | `str` | Routes history and session memory lookups. |
| `user_id` | `str` | Routes user-scoped memory lookups and result access control. |
| `run_id` | `str \| None` | Unique per `run()` call. |
| `baggage` | `dict[str, str]` | W3C Baggage key-value pairs propagated through the system. |
| `deps_json` | `str` | JSON-serialized deps (Pydantic model). |
| `deps_type_path` | `str` | Allowlisted dotted path used to deserialize `deps_json`. |
| `step` | `int` | Tool call iteration counter within a single run. |
| `retry` | `int` | Retry count for this task. |

**Key methods**

```python
def to_run_context(self) -> RunContext
```
Deserialize `deps_json` using `deps_type_path` and return a `RunContext`. Raises `AllowlistViolationError` if `deps_type_path` is not in the allowlist.

```python
@classmethod
def from_run_context(
    cls,
    ctx: RunContext,
    trace_id: str,
    span_id: str,
    session_id: str,
    user_id: str,
    baggage: dict[str, str] | None = None,
) -> "AgentRunContext"
```

```python
def to_headers(self) -> dict[str, str]
```
Serialize as HTTP headers (W3C `traceparent` + `X-Mindtrace-Baggage`).

```python
@classmethod
def from_headers(cls, headers: dict[str, str]) -> "AgentRunContext"
```

---

### `AgentTaskEnvelope`

Wire format for messages published to RabbitMQ or Redis queues. Contains everything a worker needs to reconstruct execution context.

```python
from mindtrace.agents.context.propagation import AgentTaskEnvelope
```

**Key fields**

| Field | Type | Description |
|---|---|---|
| `task_id` | `str` | UUID, auto-generated on creation. |
| `agent_name` | `str` | Name of the agent to execute. |
| `input` | `str` | User input string passed to `agent.run()`. |
| `session_id` | `str \| None` | Session identifier for history and memory loading. |
| `run_context` | `AgentRunContext` | Serialized execution context with trace IDs, user ID, and deps. |
| `provenance` | `TaskProvenance` | Submitter identity and origin gateway. Read-only for workers; logged in spans for audit. |
| `task_ttl_seconds` | `int` | Worker must begin execution before this many seconds after `submitted_at`. Default: 300 (5 minutes). |
| `result_ttl_seconds` | `int` | How long the result key lives in Redis after completion. Default: 3600 (1 hour). |
| `retry_count` | `int` | Incremented on each requeue. Capped at the queue's `max_retries`. |

---

### `CircuitBreaker` and `BackpressureConfig`

`CircuitBreaker` wraps async callables with circuit-breaker logic to prevent cascading failures when a downstream dependency becomes unresponsive.

**Requires:** `mindtrace-agents[distributed-cluster]`

```python
from mindtrace.agents.distributed.resilience import CircuitBreaker, BackpressureConfig
```

**`CircuitBreaker` Constructor**

```python
CircuitBreaker(
    name: str,
    failure_threshold: int = 5,
    window_seconds: float = 30.0,
    recovery_timeout_seconds: float = 60.0,
) -> None
```

| Parameter | Description |
|---|---|
| `name` | Human-readable name used in logs and metrics (e.g. `"task_queue"`, `"registry"`). |
| `failure_threshold` | Number of failures within `window_seconds` before the circuit opens. |
| `window_seconds` | Sliding window for counting failures. |
| `recovery_timeout_seconds` | Seconds in OPEN state before transitioning to HALF_OPEN for a probe call. |

**States:** `CLOSED` (normal) → `OPEN` (failing fast) → `HALF_OPEN` (probe) → `CLOSED` or `OPEN`.

**Key method**

```python
async def call(self, fn: Callable[..., Awaitable[T]], *args: Any, **kwargs: Any) -> T
```

Raises `CircuitOpenError` if the circuit is OPEN and the recovery timeout has not elapsed.

**`BackpressureConfig` fields**

```python
class BackpressureConfig(BaseModel):
    max_queue_depth: int = 10_000
    max_concurrent_sessions: int = 500
    queue_depth_check_interval_seconds: float = 5.0
```

The gateway uses `BackpressureConfig` to reject new task submissions when the queue is full and to close new WebSocket connections with code `1013` when the session limit is reached.

---

### `RetryPolicy`

Configurable per-queue retry policy. Pass this to `RabbitMQAgentTaskQueue` or `RedisAgentTaskQueue` at construction time.

```python
from mindtrace.agents.distributed.resilience import RetryPolicy
```

**Fields**

```python
class RetryPolicy(BaseModel):
    max_retries: int = 3
    backoff_strategy: Literal["fixed", "exponential", "jitter"] = "exponential"
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 60.0
    jitter_factor: float = 0.2
    retry_on_agent_error: bool = False
```

| Field | Description |
|---|---|
| `max_retries` | Maximum number of requeue attempts before routing to the DLQ. |
| `backoff_strategy` | `"exponential"`: delay doubles per attempt. `"fixed"`: constant delay. `"jitter"`: exponential with ± `jitter_factor` randomness. |
| `base_delay_seconds` | Initial backoff delay (and fixed delay if `backoff_strategy="fixed"`). |
| `max_delay_seconds` | Upper bound on computed backoff delay. |
| `jitter_factor` | Fractional jitter applied to exponential delays: `delay * uniform(1 - jitter_factor, 1 + jitter_factor)`. |
| `retry_on_agent_error` | If `False` (default), exceptions raised by `agent.run()` are not retried. If `True`, agent errors are treated as transient and retried up to `max_retries`. |

---

### `AbstractSkill` and `AbstractModelProviderPlugin`

Base classes for third-party skill and model provider plugins discovered via Python entry-points.

```python
from mindtrace.agents.plugins.skill import AbstractSkill
from mindtrace.agents.plugins.providers import AbstractModelProviderPlugin
```

**`AbstractSkill`**

Extends `AbstractToolset` — skills are drop-in toolsets with no agent-side changes required.

| Abstract property / method | Description |
|---|---|
| `skill_name: str` | Unique name used in `AgentDefinition.required_skills`. |
| `skill_version: str` | Semantic version string. |
| `skill_description: str` | Optional description returned in plugin listings. |
| `async setup() -> None` | Called once after discovery. Initialize connections and clients here. |
| `async teardown() -> None` | Called on worker shutdown. Close connections and release resources here. |

**`AbstractModelProviderPlugin`**

Extends `Provider`.

| Abstract property | Description |
|---|---|
| `provider_name: str` | Unique name used in `AgentDefinition.required_provider`. |
| `supported_model_ids: list[str]` | List of model IDs this provider can serve. |

**Entry-point registration**

```toml
# pyproject.toml of the skill package
[project.entry-points."mindtrace.skills"]
my_skill = "my_package.skills:MySkill"

[project.entry-points."mindtrace.model_providers"]
my_provider = "my_package.providers:MyProvider"
```

---

### `MindtracePluginRegistry`

Discovers and manages skills and model providers registered via Python entry-points.

```python
from mindtrace.agents.plugins.registry import MindtracePluginRegistry
```

**Constructor**

```python
MindtracePluginRegistry(**kwargs: Any) -> None
```

**Key methods**

```python
def discover(self) -> None
```
Scan `importlib.metadata.entry_points()` for `mindtrace.skills` and `mindtrace.model_providers` groups. Instantiate each class and call `setup()`. Call this once at worker startup.

```python
def get_skill(self, name: str) -> AbstractSkill
def get_provider(self, name: str) -> AbstractModelProviderPlugin
def list_skills(self) -> list[SkillInfo]
def list_providers(self) -> list[ProviderInfo]
```

---

### Wire Protocol Models

These Pydantic models define every message exchanged between the client and the gateway over WebSocket (and REST). Import them from:

```python
from mindtrace.agents.distributed.types import (
    AgentInvokeRequest,
    AgentSessionMessage,
    AgentAckMessage,
    AgentStreamEvent,
    AgentInvokeResponse,
    AgentErrorMessage,
    TokenUsage,
)
```

#### `AgentInvokeRequest` (Client → Gateway)

```python
class AgentInvokeRequest(BaseModel):
    agent_name: str
    input: str
    session_id: str | None = None   # omit to start a new session
    deps: dict[str, Any] = {}
    stream: bool = True             # False → wait for full result (REST-style)
    metadata: dict[str, Any] = {}
```

#### `AgentSessionMessage` (Gateway → Client, on connect)

```python
class AgentSessionMessage(BaseModel):
    type: Literal["connected"] = "connected"
    session_id: str
    gateway_id: str
```

#### `AgentAckMessage` (Gateway → Client, after enqueue)

```python
class AgentAckMessage(BaseModel):
    type: Literal["ack"] = "ack"
    task_id: str
    trace_id: str
```

#### `AgentStreamEvent` (Gateway → Client, per streaming frame)

```python
class AgentStreamEvent(BaseModel):
    type: Literal["stream_event"] = "stream_event"
    task_id: str
    trace_id: str
    event_kind: Literal["part_start", "part_delta", "part_end", "tool_result", "result"]
    payload: dict[str, Any]   # serialized NativeEvent fields
```

Token text arrives in `event_kind="part_delta"` frames. Read `payload["delta"]` for the incremental text.

#### `AgentInvokeResponse` (Gateway → Client, on completion)

```python
class AgentInvokeResponse(BaseModel):
    type: Literal["response"] = "response"
    task_id: str
    trace_id: str
    span_id: str
    session_id: str
    output: Any
    usage: TokenUsage | None = None
```

#### `AgentErrorMessage` (Gateway → Client, on failure)

```python
class AgentErrorMessage(BaseModel):
    type: Literal["error"] = "error"
    task_id: str | None = None
    trace_id: str
    code: str       # "auth_failed" | "agent_not_found" | "timeout" | "execution_error" | "service_unavailable"
    message: str
```

#### `TokenUsage`

```python
class TokenUsage(BaseModel):
    input_tokens: int
    output_tokens: int
    model_name: str
```

---

## 5. Authentication Guide

### Principals and Trust Levels

| Principal | Credential | What they may do |
|---|---|---|
| **Human user** | Bearer JWT (OIDC) | Submit tasks, read their own results, disconnect own sessions |
| **Service account** | HMAC-SHA256 API key (`X-Mindtrace-Api-Key`) | Submit tasks, read any task result, list agents |
| **Worker** | Internal secret (`X-Mindtrace-Worker-Token`) | Register/heartbeat/deregister in registry; POST spans to collector |
| **Admin** | Service-account key with `role=admin` claim | Register/delete agent definitions, manage allowlist, drain DLQ |

No unauthenticated requests are permitted on any endpoint.

### Passing a JWT Bearer Token (WebSocket)

Include the `Authorization` header in the WebSocket upgrade request:

```python
import websockets

async with websockets.connect(
    "ws://gateway:8000/ws/agents",
    additional_headers={"Authorization": "Bearer <your-jwt-token>"},
) as ws:
    ...
```

Alternatively, pass the token as a query parameter (useful when the WebSocket client library does not support custom headers):

```
ws://gateway:8000/ws/agents?token=<your-jwt-token>
```

Token precedence: `Authorization` header takes priority over the `token` query parameter.

### Passing an API Key (Service Accounts)

```python
import websockets

async with websockets.connect(
    "ws://gateway:8000/ws/agents",
    additional_headers={"X-Mindtrace-Api-Key": "<your-api-key>"},
) as ws:
    ...
```

For REST endpoints:

```python
import httpx
httpx.post(
    "http://gateway:8000/agents/my_agent/invoke",
    json={...},
    headers={"X-Mindtrace-Api-Key": "<your-api-key>"},
)
```

### Authorization Scopes

| Scope | Required for |
|---|---|
| `tasks:submit` | `POST /agents/{name}/invoke`, WebSocket `AgentInvokeRequest` |
| `tasks:read` | `GET /agents/{name}/tasks/{task_id}`, result retrieval |
| `tasks:cancel` | Calling `cancel()` on a task queue |
| `agents:list` | `GET /agents/` |
| `agents:manage` | Registering or deleting `AgentDefinition` entries |
| `dlq:manage` | Inspecting and requeueing from the DLQ |
| `allowlist:manage` | Adding or removing allowlist entries |
| `spans:ingest` | `POST /spans` on `AgentObservabilityCollector` (workers only) |
| `metrics:read` | `GET /metrics` on `AgentObservabilityCollector` |

Scopes are encoded in the JWT `scopes` claim or in the API key metadata stored in Redis. The gateway enforces scopes before processing any request.

A user-scoped principal may only retrieve results for tasks they submitted. Service accounts and admins may access any task result.

### JWT Validation Configuration

The gateway validates JWT signatures using the JWKS endpoint of your identity provider. Set the following environment variable before starting the gateway:

```bash
export MINDTRACE_JWKS_URL="https://your-idp.example.com/.well-known/jwks.json"
```

Mindtrace does not issue tokens. Use any OIDC-compliant identity provider (Keycloak, Auth0, Okta) to issue JWTs. The gateway verifies the signature, expiry, and required scopes.

### Worker-to-Registry Authentication

Workers present a shared internal secret in the `X-Mindtrace-Worker-Token` header when registering and sending heartbeats. Set this secret on every node:

```bash
export MINDTRACE_INTERNAL_SECRET="<256-bit-random-value>"
```

The registry validates this with a constant-time comparison. Rotate the secret via your orchestration layer (Kubernetes Secret, Docker Secret). Do not hard-code it.

---

## 6. Memory Architecture

### Namespace Model

The library uses a five-level namespace hierarchy. Choose the namespace that matches the lifetime and isolation you need:

| Scope | Backend | Key Pattern | Default TTL | When to use |
|---|---|---|---|---|
| per-task | Redis | `task:{task_id}:{key}` | task lifetime | Intermediate tool results within a single agent run |
| per-session | Redis | `session:{session_id}:{key}` | 1 hour | Conversation working memory shared across turns of one session |
| per-agent | MongoDB | `agent:{name}:{key}` | permanent | Agent-specific knowledge base, cached documents |
| per-user | MongoDB | `user:{user_id}:{key}` | permanent | User preferences, long-term facts about a user |
| global | MongoDB | `global:{key}` | permanent | Shared knowledge accessible to all agents and users |

### Using `RedisMemoryStore` (short-term)

```python
from mindtrace.agents.memory.redis import RedisMemoryStore

# Per-session memory
session_mem = RedisMemoryStore(
    redis_url="redis://localhost:6379",
    namespace="session:sess-001",
    default_ttl=3600,
)

# Write a value
await session_mem.save("user_intent", "book a flight to Tokyo")

# Read it back
entry = await session_mem.get("user_intent")
print(entry.value)  # "book a flight to Tokyo"

# List all keys in this namespace
keys = await session_mem.list_keys()

# Per-task memory (shorter TTL)
task_mem = RedisMemoryStore(
    redis_url="redis://localhost:6379",
    namespace="task:task-abc123",
    default_ttl=300,   # expires 5 minutes after last write
)
await task_mem.save("search_results", "...", ttl=120)  # per-entry TTL override
```

### Using `MongoMemoryStore` without vector search

```python
from mindtrace.agents.memory.mongo import MongoMemoryStore

# Per-user long-term memory, text search only
user_mem = MongoMemoryStore(
    mongo_url="mongodb://mongo:27017",
    database="mindtrace",
    collection="agent_memory",
    namespace="user:user-42",
)

await user_mem.save(
    key="home_city",
    value="Amsterdam",
    metadata={"updated_at": "2026-04-14"},
)

# $text search (requires a MongoDB text index on the `value` field)
results = await user_mem.search("city", top_k=5)
for r in results:
    print(r.key, r.value)
```

### Using `MongoMemoryStore` with vector search

```python
from mindtrace.agents.memory.mongo import MongoMemoryStore, EmbeddingProvider
import openai

class OpenAIEmbedder:
    """EmbeddingProvider implementation using OpenAI embeddings."""

    async def embed(self, text: str) -> list[float]:
        client = openai.AsyncOpenAI()
        response = await client.embeddings.create(
            model="text-embedding-3-small",
            input=text,
        )
        return response.data[0].embedding


# Per-agent knowledge base with vector search
agent_mem = MongoMemoryStore(
    mongo_url="mongodb://mongo:27017",
    database="mindtrace",
    collection="agent_memory",
    namespace="agent:research_agent",
    embedding_provider=OpenAIEmbedder(),
    vector_index_name="vector_index",
)

await agent_mem.save("doc_001", "The capital of France is Paris.")
await agent_mem.save("doc_002", "Paris is known for the Eiffel Tower.")

# Semantic similarity search
results = await agent_mem.search("French cities and landmarks", top_k=3)
for r in results:
    print(r.key, r.value)
```

> **Note:** Vector search requires a MongoDB Atlas Search vector index named `vector_index_name` on the `value_embedding` field of your collection. If `embedding_provider` is not set, or if the vector index is not configured, `MongoMemoryStore` falls back to MongoDB `$text` search automatically.

---

## 7. Error Handling and Retries

### Error Codes in `AgentErrorMessage`

When a task fails, the gateway sends an `AgentErrorMessage` over WebSocket (or returns a 4xx/5xx HTTP response for REST). The `code` field identifies the failure type:

| Code | Cause | Retryable by client? |
|---|---|---|
| `auth_failed` | Token missing, expired, or invalid signature | No — re-authenticate first |
| `agent_not_found` | No `AgentDefinition` registered for the requested `agent_name` | No — register the agent first |
| `timeout` | Task TTL expired before a worker picked it up, or `get_result()` timed out | Yes — resubmit |
| `execution_error` | `agent.run()` raised an unhandled exception | Depends on `retry_on_agent_error` |
| `service_unavailable` | Queue circuit-breaker is OPEN or queue depth exceeded `max_queue_depth` | Yes — retry after a short delay |

### Configuring `RetryPolicy`

```python
from mindtrace.agents.distributed.resilience import RetryPolicy
from mindtrace.agents.execution.rabbitmq import RabbitMQAgentTaskQueue

policy = RetryPolicy(
    max_retries=5,
    backoff_strategy="jitter",
    base_delay_seconds=2.0,
    max_delay_seconds=120.0,
    jitter_factor=0.3,
    retry_on_agent_error=False,   # deterministic agent failures are not retried
)

queue = RabbitMQAgentTaskQueue(
    rabbitmq_url="amqp://localhost/",
    redis_url="redis://localhost:6379",
    max_retries=policy.max_retries,
)
```

### Inspecting and Requeueing from the DLQ

Tasks route to the DLQ when:
- `retry_count >= max_retries`
- Task TTL is exceeded
- An `AllowlistViolationError` or `ValidationError` occurs (not retried automatically)

Use the admin CLI to inspect and requeue:

```bash
# List messages in the DLQ
mindtrace agents inspect-dlq

# Requeue a specific task (resets retry_count to 0)
mindtrace agents requeue-dlq --task-id <task_id>

# Requeue all tasks from the DLQ
mindtrace agents requeue-dlq --all
```

Programmatically:

```python
await task_queue.requeue_from_dlq(task_id="<task_id>")
```

> **Warning:** Do not requeue tasks that failed with `AllowlistViolationError` or `ValidationError` without investigating the root cause first. These failures are deterministic — requeueing will fail again unless the underlying issue (unregistered agent class, schema mismatch) is resolved.

### Task TTL and Result Expiry

Each `AgentTaskEnvelope` carries two TTL fields:

- `task_ttl_seconds` (default: 300): The worker must begin execution within this many seconds of `submitted_at`. Tasks that arrive stale are routed to the DLQ.
- `result_ttl_seconds` (default: 3600): The Redis result key expires this many seconds after completion. Callers that miss this window receive a `ResultExpiredError`.

For long-running agents, increase these values at task submission time via `metadata` or by configuring the queue defaults.

---

## 8. Deployment Checklist

Use this checklist when deploying a distributed Mindtrace agent system.

### Required Infrastructure

| Component | Purpose | Notes |
|---|---|---|
| **Redis** | Task queue (Redis backend), session history, session memory, result storage, worker registry, allowlist | Required for any distributed deployment |
| **RabbitMQ** | Primary task queue for production workloads | Required when using `RabbitMQAgentTaskQueue`. Enable the delayed-message plugin for retry backoff. |
| **MongoDB** | Long-term agent and user memory, span storage | Optional; required only if using `MongoMemoryStore` or `AgentObservabilityCollector` with persistence |
| **OTLP endpoint** | Distributed trace export | Optional; Jaeger (`jaeger:4318`) or Grafana Tempo |

### Required Environment Variables

Set these on every gateway, worker, node, and collector process:

```bash
# JWT validation — required for human user authentication
MINDTRACE_JWKS_URL="https://your-idp.example.com/.well-known/jwks.json"

# Worker-to-registry authentication — required on all workers and nodes
MINDTRACE_INTERNAL_SECRET="<256-bit-random-value>"

# Observability — optional; omit if not using the collector
MINDTRACE_COLLECTOR_URL="http://collector:8001"
```

### Pre-Flight Steps

1. **Start Redis and RabbitMQ** before any Mindtrace process.
2. **Seed the allowlist** for every agent class and deps type your deployment uses:
   ```bash
   mindtrace agents allowlist-add --path "myapp.agents:MyAgent" --type agent_class
   mindtrace agents allowlist-add --path "myapp.deps:MyDeps" --type deps_type
   ```
3. **Register agent definitions** in the registry:
   ```bash
   # Or use the Python API in your deploy script
   mindtrace agents register --name my_agent --class "myapp.agents:MyAgent"
   ```
4. **Start the observability collector** (if using), then the gateway, then workers.
5. **Verify health** of all services before routing production traffic:
   ```bash
   curl http://gateway:8000/health
   curl http://collector:8001/health
   ```

### Scaling Workers

Workers are horizontally scalable. Add more worker processes or machines at any time — they register themselves in the shared `MindtraceAgentRegistry` and begin consuming from the shared RabbitMQ queue immediately. No gateway configuration change is needed.

Workers expose concurrency control via `max_concurrent_agents` (default: 4). Tune this based on your model API rate limits and available memory.

### Health and Readiness Probes

Use `GET /health` for Kubernetes liveness and readiness probes. The endpoint is unauthenticated and returns a `HealthStatus` model with per-component status. A `status: "ok"` response indicates the service and all its dependencies are reachable.

```yaml
# Kubernetes liveness probe example
livenessProbe:
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 10
  periodSeconds: 15
```

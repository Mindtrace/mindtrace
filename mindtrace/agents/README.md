# mindtrace-agents

Agent framework for the Mindtrace platform. Build LLM-powered agents with tool use, conversation history, lifecycle callbacks, and pluggable model providers — all integrated with Mindtrace logging and configuration.

## Installation

```bash
uv add mindtrace-agents
# or
pip install mindtrace-agents
```

---

## Core Concepts

| Concept | Class | What it does |
|---------|-------|-------------|
| **Agent** | `MindtraceAgent` | Orchestrates model + tools, runs the conversation loop |
| **Model** | `OpenAIChatModel` | Calls the LLM API (supports streaming) |
| **Provider** | `OpenAIProvider` / `OllamaProvider` / `GeminiProvider` | Holds the authenticated client |
| **Tool** | `Tool` | Wraps a Python function for LLM tool-calling |
| **Toolset** | `FunctionToolset` / `CompoundToolset` / `MCPToolset` | Groups tools and controls which are exposed to the agent |
| **ToolFilter** | `ToolFilter` | Predicate for selectively showing/hiding tools by name or description |
| **Callbacks** | `AgentCallbacks` | Lifecycle hooks: before/after LLM call and tool call |
| **History** | `AbstractHistoryStrategy` / `InMemoryHistory` | Persists conversation across runs |
| **RunContext** | `RunContext[T]` | Injected into tools — carries deps, retry count, step |
| **Memory** | `MemoryToolset` / `InMemoryStore` / `JsonFileStore` | Agent-controlled persistent memory exposed as tools |
| **Task Queue** | `LocalTaskQueue` / `RabbitMQTaskQueue` | Distribute agent execution across processes or workers |
| **DistributedAgent** | `DistributedAgent` | Transparent wrapper that routes `run()` through a task queue |

---

## Quick Start

### Basic agent with OpenAI

```python
import asyncio
from mindtrace.agents import MindtraceAgent, OpenAIChatModel, OpenAIProvider

provider = OpenAIProvider()  # reads OPENAI_API_KEY from env
model = OpenAIChatModel("gpt-4o-mini", provider=provider)

agent = MindtraceAgent(
    model=model,
    system_prompt="You are a helpful assistant.",
    name="my_agent",
)

result = asyncio.run(agent.run("What is 2 + 2?"))
print(result)  # "4"
```

### With Ollama (local)

```python
from mindtrace.agents import MindtraceAgent, OpenAIChatModel, OllamaProvider

provider = OllamaProvider(base_url="http://localhost:11434/v1")
model = OpenAIChatModel("llama3.2", provider=provider)
agent = MindtraceAgent(model=model, name="local_agent")
```

### With Gemini

```python
from mindtrace.agents import MindtraceAgent, OpenAIChatModel, GeminiProvider

provider = GeminiProvider()  # reads GEMINI_API_KEY from env
model = OpenAIChatModel("gemini-2.0-flash", provider=provider)
agent = MindtraceAgent(model=model, name="gemini_agent")
```

---

## Adding Tools

Tools are Python functions (sync or async). Annotate parameters with types — these become the JSON schema shown to the model.

```python
from mindtrace.agents import MindtraceAgent, OpenAIChatModel, OpenAIProvider, Tool, RunContext

def get_weather(ctx: RunContext[None], city: str) -> str:
    """Get the current weather for a city."""
    return f"Weather in {city}: Sunny, 22°C"

async def search_web(query: str, max_results: int = 5) -> list[str]:
    """Search the web and return URLs."""
    # ctx is optional — omit it for plain tools
    return [f"https://example.com/result/{i}" for i in range(max_results)]

provider = OpenAIProvider()
model = OpenAIChatModel("gpt-4o-mini", provider=provider)

agent = MindtraceAgent(
    model=model,
    tools=[Tool(get_weather), Tool(search_web)],
    system_prompt="You have access to weather and search tools.",
)

result = asyncio.run(agent.run("What's the weather in Paris?"))
```

### Tool with dependencies (typed deps)

```python
from dataclasses import dataclass

@dataclass
class AppDeps:
    db_url: str
    api_key: str

def lookup_user(ctx: RunContext[AppDeps], user_id: str) -> dict:
    """Look up a user by ID."""
    # ctx.deps is your AppDeps instance
    return {"id": user_id, "db": ctx.deps.db_url}

deps = AppDeps(db_url="postgresql://...", api_key="secret")
result = asyncio.run(agent.run("Find user 123", deps=deps))
```

---

## Toolsets

Toolsets are the primary way to supply tools to an agent. They group related tools together and give you control over which tools are visible to the model at runtime.

### FunctionToolset

`FunctionToolset` collects Python `Tool` objects and exposes them to the agent. Use it when you want to organise tools manually or share a toolset across multiple agents.

```python
from mindtrace.agents.toolsets import FunctionToolset
from mindtrace.agents.tools import Tool

def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b

async def fetch(url: str) -> str:
    """Fetch a URL."""
    ...

toolset = FunctionToolset(max_retries=2)
toolset.add_tool(Tool(add))
toolset.add_tool(Tool(fetch))

agent = MindtraceAgent(model=model, toolset=toolset)
```

`max_retries` on the toolset is the default for every tool added to it. Override per-tool by setting `Tool(..., max_retries=N)` before calling `add_tool()`.

### CompoundToolset

`CompoundToolset` merges tools from multiple toolsets into one. Later toolsets win on name collisions — use `prefix` on `MCPToolset` to avoid conflicts.

```python
from mindtrace.agents.toolsets import CompoundToolset, FunctionToolset

agent = MindtraceAgent(
    model=model,
    toolset=CompoundToolset(
        MCPToolset.from_http("http://localhost:8001/mcp-server/mcp/"),
        FunctionToolset(),   # local tools
    ),
)
```

### MCPToolset

`MCPToolset` exposes tools from any remote MCP server. Requires `fastmcp`:

```bash
pip install 'mindtrace-agents[mcp]'
```

**Constructors**

```python
from mindtrace.agents.toolsets import MCPToolset

# HTTP (streamable-http) — default for Mindtrace services
ts = MCPToolset.from_http("http://localhost:8001/mcp-server/mcp/")

# SSE (legacy HTTP)
ts = MCPToolset.from_sse("http://localhost:9000/sse")

# stdio — local subprocess servers (e.g. npx)
ts = MCPToolset.from_stdio(["npx", "-y", "@modelcontextprotocol/server-filesystem", "/tmp"])
```

**Prefix** — avoid name collisions when combining multiple MCP services:

```python
ts = MCPToolset.from_http("http://localhost:8002/mcp/", prefix="db")
# tools are exposed as "db__query", "db__list_tables", etc.
```

---

## Filtering tools

Every toolset exposes shorthand methods that return a `FilteredToolset`. Chain them to control exactly which tools the agent sees.

```python
# Allow only named tools
toolset.include("search", "summarise")

# Block a specific tool
toolset.exclude("drop_table")

# Glob patterns
toolset.include_pattern("read_*", "list_*")
toolset.exclude_pattern("admin_*")

# Compose via FilteredToolset.with_filter() for boolean logic
from mindtrace.agents.toolsets import ToolFilter

f = ToolFilter.include_pattern("read_*") & ~ToolFilter.include("read_credentials")
toolset.with_filter(f)
```

Filtering applies at `get_tools()` time — the underlying toolset is unchanged.

### ToolFilter API

| Factory | Behaviour |
|---------|-----------|
| `ToolFilter.include(*names)` | Allow only tools whose name is in `names` |
| `ToolFilter.exclude(*names)` | Block tools whose name is in `names` |
| `ToolFilter.include_pattern(*globs)` | Allow tools matching any glob (e.g. `"read_*"`) |
| `ToolFilter.exclude_pattern(*globs)` | Block tools matching any glob |
| `ToolFilter.by_description(fn)` | Custom predicate on the tool description string |

Filters compose with `&` (AND), `|` (OR), and `~` (NOT).

### Combining filtering with CompoundToolset

```python
agent = MindtraceAgent(
    model=model,
    toolset=CompoundToolset(
        MCPToolset.from_http("http://localhost:8001/mcp/").include("generate_image"),
        MCPToolset.from_http("http://localhost:8002/mcp/").exclude_pattern("admin_*"),
        FunctionToolset(),
    ),
)
```

---

## Lifecycle Callbacks

Attach async or sync callbacks to hook into the agent's execution.

```python
from mindtrace.agents import MindtraceAgent, AgentCallbacks

def log_before_llm(messages, model_settings):
    print(f"Sending {len(messages)} messages to LLM")
    # Return (messages, model_settings) to modify, or None to keep unchanged
    return None

async def log_after_tool(tool_name, args, result, ctx):
    print(f"Tool {tool_name!r} returned: {result}")
    # Return modified result or None to keep unchanged
    return None

callbacks = AgentCallbacks(
    before_llm_call=log_before_llm,
    after_llm_call=None,         # (response) -> response | None
    before_tool_call=None,       # (tool_name, args, ctx) -> (name, args) | None
    after_tool_call=log_after_tool,
)

agent = MindtraceAgent(model=model, tools=[...], callbacks=callbacks)
```

### Callback signatures

| Callback | Arguments | Return |
|----------|-----------|--------|
| `before_llm_call` | `(messages: list, model_settings: dict\|None)` | `(messages, model_settings)` or `None` |
| `after_llm_call` | `(response: ModelResponse)` | `ModelResponse` or `None` |
| `before_tool_call` | `(tool_name: str, args: str, ctx: RunContext)` | `(tool_name, args)` or `None` |
| `after_tool_call` | `(tool_name: str, args: str, result: Any, ctx: RunContext)` | modified result or `None` |

All callbacks can be **sync or async** — the framework handles both transparently.

---

## Conversation History

Pass `session_id` to `run()` to automatically persist and reload conversation history.

```python
from mindtrace.agents import MindtraceAgent, InMemoryHistory

history = InMemoryHistory()

agent = MindtraceAgent(
    model=model,
    history=history,
    system_prompt="You are a helpful assistant.",
)

# First turn — history is empty, gets saved under "user-123"
reply1 = asyncio.run(agent.run("My name is Alice.", session_id="user-123"))

# Second turn — history is loaded automatically, agent remembers Alice
reply2 = asyncio.run(agent.run("What's my name?", session_id="user-123"))
# → "Your name is Alice."
```

### Custom history backend

Implement `AbstractHistoryStrategy` to persist history anywhere (Redis, MongoDB, etc.):

```python
from mindtrace.agents import AbstractHistoryStrategy, ModelMessage

class RedisHistory(AbstractHistoryStrategy):
    async def load(self, session_id: str) -> list[ModelMessage]:
        data = await redis.get(f"history:{session_id}")
        return deserialize(data) if data else []

    async def save(self, session_id: str, messages: list[ModelMessage]) -> None:
        await redis.set(f"history:{session_id}", serialize(messages))

    async def clear(self, session_id: str) -> None:
        await redis.delete(f"history:{session_id}")
```

---

## Streaming

Use `run_stream_events()` to receive events as the model generates tokens:

```python
from mindtrace.agents import PartDeltaEvent, PartStartEvent, ToolResultEvent, AgentRunResultEvent

async def stream_example():
    async for event in agent.run_stream_events("Tell me a joke", session_id="s1"):
        if isinstance(event, PartStartEvent) and event.part_kind == "text":
            print("\n[Text started]")
        elif isinstance(event, PartDeltaEvent):
            if hasattr(event.delta, "content_delta"):
                print(event.delta.content_delta, end="", flush=True)
        elif isinstance(event, ToolResultEvent):
            print(f"\n[Tool result: {event.content}]")
        elif isinstance(event, AgentRunResultEvent):
            print(f"\n[Done: {event.result.output}]")

asyncio.run(stream_example())
```

---

## Step-by-step iteration

Use `iter()` for fine-grained control over the execution loop:

```python
async def iterate_example():
    async with agent.iter("What's 15% of 240?") as steps:
        async for step in steps:
            if step["step"] == "model_response":
                print(f"LLM said: {step['text']}")
                print(f"Tool calls: {step['tool_calls']}")
            elif step["step"] == "tool_result":
                print(f"Tool {step['tool_name']} → {step['result']}")
            elif step["step"] == "complete":
                print(f"Final answer: {step['result']}")
```

---

## WrapperAgent

Compose agents or add cross-cutting behaviour without modifying base classes:

```python
from mindtrace.agents import WrapperAgent

class TimedAgent(WrapperAgent):
    async def run(self, input_data, *, deps=None, **kwargs):
        import time
        start = time.monotonic()
        result = await super().run(input_data, deps=deps, **kwargs)
        self.logger.info(f"Run took {time.monotonic() - start:.2f}s")
        return result

timed = TimedAgent(agent)
result = asyncio.run(timed.run("Hello"))
```

---

## Sync usage

```python
result = agent.run_sync("What is the capital of France?")
# → "Paris"
```

---

## Logging and config

All agents, models, and providers inherit from `MindtraceABC` and automatically receive:

- `self.logger` — a structured logger scoped to the class name
- `self.config` — the `CoreConfig` instance

```python
agent.logger.info("Starting run", session_id="abc")
```

---

---

## Multi-Agent Coworking

Agents are first-class tools. Pass any `MindtraceAgent` directly into `tools=[]` alongside regular `Tool` objects — the framework converts it automatically.

```python
researcher = MindtraceAgent(
    model=model,
    name="researcher",
    description="Research a topic and return facts",  # shown to LLM as tool description
    tools=[web_search_tool],
)

writer = MindtraceAgent(
    model=model,
    name="writer",
    description="Write a structured report from given facts",
    tools=[format_tool],
)

orchestrator = MindtraceAgent(
    model=model,
    tools=[researcher, writer, some_regular_tool],  # mix freely
)

result = await orchestrator.run("Write a report on climate change")
```

The `description` field is required when using an agent as a tool — it's what the LLM reads to decide when to call it. Parent `deps` are forwarded to sub-agents automatically via `RunContext`.

### Context exchange between agents

| Deployment | Mechanism |
|---|---|
| Same process | `deps` carries shared state directly — mutations visible across agents |
| Distributed workers | `deps` carries a **client** (Redis, DB) — workers read/write through it, not raw data |

`deps` is serialised when submitted to a task queue. Don't put live in-memory objects in deps for distributed use — put connection config and reconnect on the worker side.

### HandoffPart

Use `HandoffPart` to mark an explicit handoff boundary in an agent's message history. Useful for observability and keeping sub-agent history scoped:

```python
from mindtrace.agents import HandoffPart

part = HandoffPart(
    from_agent="orchestrator",
    to_agent="writer",
    summary="Researcher found: sea levels rose 20cm since 1980",
)
```

---

## Agent Memory

`MemoryToolset` exposes persistent memory as LLM-callable tools. The agent decides what to save and when to recall — no code wiring needed.

```python
from mindtrace.agents import MindtraceAgent, MemoryToolset, JsonFileStore, CompoundToolset
from mindtrace.agents.toolsets import FunctionToolset

memory = JsonFileStore("./agent_memory.json")  # persists across restarts

agent = MindtraceAgent(
    model=model,
    toolset=CompoundToolset(
        FunctionToolset([my_tools]),
        MemoryToolset(memory, namespace="user_123"),
    ),
)
```

**Tools exposed to the agent:**

| Tool | Args | Effect |
|---|---|---|
| `save_memory` | `key, value` | Persist a fact |
| `recall_memory` | `key` | Retrieve by key |
| `search_memory` | `query, top_k=5` | Substring search across all memories |
| `forget_memory` | `key` | Delete an entry |
| `list_memories` | — | List all keys |

The `namespace` parameter scopes entries per-user or per-session — two `MemoryToolset` instances on the same store with different namespaces never see each other's data.

### Memory backends

| Class | Persistence | `search()` |
|---|---|---|
| `InMemoryStore` | None (lost on restart) | Substring |
| `JsonFileStore` | Local `.json` file | Substring |

Implement `AbstractMemoryStore` for custom backends (Redis, vector DB, etc.). The only method that varies meaningfully is `search()` — simple backends use substring, vector backends use embeddings.

```python
from mindtrace.agents import AbstractMemoryStore, MemoryEntry

class RedisMemoryStore(AbstractMemoryStore):
    async def save(self, key, value, metadata=None): ...
    async def get(self, key) -> MemoryEntry | None: ...
    async def search(self, query, top_k=5) -> list[MemoryEntry]: ...
    async def delete(self, key): ...
    async def list_keys(self) -> list[str]: ...
```

Install optional extras for third-party backends:

```bash
pip install 'mindtrace-agents[memory-redis]'   # Redis
pip install 'mindtrace-agents[memory-vector]'  # ChromaDB
```

---

## Distributed Execution

### Task queues

`AbstractTaskQueue` decouples task submission from execution. Use `LocalTaskQueue` for single-process orchestration, `RabbitMQTaskQueue` for multi-worker deployments.

```python
from mindtrace.agents import LocalTaskQueue, AgentTask

queue = LocalTaskQueue()
queue.register(researcher)   # agents must be registered by name

task_id = await queue.submit(AgentTask(
    agent_name="researcher",
    input="What caused the 2008 financial crisis?",
    deps=my_deps,
    session_id="s1",
))
result = await queue.get_result(task_id)
```

`TaskStatus` values: `PENDING → RUNNING → DONE | FAILED`

### DistributedAgent

`DistributedAgent` wraps any agent and routes `run()` through a task queue. The API is identical to `MindtraceAgent` — callers don't need to change.

```python
from mindtrace.agents import DistributedAgent

distributed_researcher = DistributedAgent(researcher, task_queue=queue)
result = await distributed_researcher.run("Research topic")  # executes via queue
```

### RabbitMQ

Requires `aio-pika`:

```bash
pip install 'mindtrace-agents[distributed-rabbitmq]'
```

**Caller side** (submit tasks):

```python
from mindtrace.agents.execution.rabbitmq import RabbitMQTaskQueue

queue = RabbitMQTaskQueue(url="amqp://guest:guest@localhost/")
distributed = DistributedAgent(researcher, task_queue=queue)
result = await distributed.run("Research topic")
```

**Worker side** (consume and execute):

```python
queue = RabbitMQTaskQueue(url="amqp://guest:guest@localhost/")
await queue.serve(researcher)  # blocks; run N replicas for parallelism
```

RabbitMQ round-robins tasks across replicas automatically. `AgentTask` is serialised with `pickle` — `deps` must be pickle-serialisable. For cross-process use, put connection config in `deps` (not live connections).

---

## Package layout

```
mindtrace/agents/
├── __init__.py          # public API
├── _run_context.py      # RunContext dataclass
├── _function_schema.py  # type introspection + Pydantic validation
├── _tool_manager.py     # tool dispatch + retry
├── prompts.py           # UserPromptPart, BinaryContent, ImageUrl
├── profiles/            # ModelProfile capability flags
├── events/              # streaming event types
├── messages/            # ModelMessage, parts (incl. HandoffPart), builder
├── tools/               # Tool, ToolDefinition
├── toolsets/            # AbstractToolset, FunctionToolset, CompoundToolset, MCPToolset, ToolFilter, FilteredToolset
├── providers/           # Provider ABC + OpenAI, Ollama, Gemini
├── models/              # Model ABC + OpenAIChatModel
├── callbacks/           # AgentCallbacks + _invoke helper
├── history/             # AbstractHistoryStrategy + InMemoryHistory
├── memory/              # AbstractMemoryStore, InMemoryStore, JsonFileStore, MemoryToolset
├── execution/           # AbstractTaskQueue, AgentTask, LocalTaskQueue, RabbitMQTaskQueue
└── core/                # AbstractMindtraceAgent, MindtraceAgent, WrapperAgent, DistributedAgent
```

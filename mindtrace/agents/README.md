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
├── messages/            # ModelMessage, parts, builder
├── tools/               # Tool, ToolDefinition
├── toolsets/            # AbstractToolset, FunctionToolset, CompoundToolset, MCPToolset, ToolFilter, FilteredToolset
├── providers/           # Provider ABC + OpenAI, Ollama, Gemini
├── models/              # Model ABC + OpenAIChatModel
├── callbacks/           # AgentCallbacks + _invoke helper
├── history/             # AbstractHistoryStrategy + InMemoryHistory
└── core/                # AbstractMindtraceAgent, MindtraceAgent, WrapperAgent
```

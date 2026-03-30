[![PyPI version](https://img.shields.io/pypi/v/mindtrace-agents)](https://pypi.org/project/mindtrace-agents/)
[![License](https://img.shields.io/pypi/l/mindtrace-agents)](https://github.com/mindtrace/mindtrace/blob/main/mindtrace/agents/LICENSE)
[![Downloads](https://static.pepy.tech/badge/mindtrace-agents)](https://pepy.tech/projects/mindtrace-agents)

# Mindtrace Agents

The `Agents` module provides Mindtrace’s framework for building LLM-powered agents with tool use, conversation history, memory, callbacks, streaming, and distributed execution.

## Features

- **Agent runtime** with `MindtraceAgent`
- **Pluggable models and providers** for OpenAI, Ollama, and Gemini
- **Tool calling** with Python functions, toolsets, and remote MCP tools
- **Lifecycle control** with callbacks, streaming events, and step-by-step iteration
- **State and persistence** with history backends and memory toolsets
- **Multi-agent composition** with agents-as-tools and handoff markers
- **Distributed execution** with local and RabbitMQ-backed task queues

## Quick Start

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
print(result)
```

In practice, a `MindtraceAgent` coordinates four things:

- a **model** that generates responses
- a **provider** that talks to the backend API
- optional **tools** or **toolsets** the model may call
- optional **history**, **memory**, and **callbacks** around the run loop

## MindtraceAgent

`MindtraceAgent` is the central runtime in the package. It runs the conversation loop:

1. build the message list
2. call the model
3. expose tools to the model when available
4. execute tool calls and append results back into the conversation
5. return the final output

A minimal agent looks like this:

```python
from mindtrace.agents import MindtraceAgent, OpenAIChatModel, OpenAIProvider


provider = OpenAIProvider()
model = OpenAIChatModel("gpt-4o-mini", provider=provider)

agent = MindtraceAgent(model=model, name="assistant")
```

## Models and Providers

Models and providers are related, but they are not the same thing.

- a **provider** holds the authenticated backend client or connection details
- a **model** implements the request/response interface for a specific model family

### OpenAI

```python
from mindtrace.agents import MindtraceAgent, OpenAIChatModel, OpenAIProvider


provider = OpenAIProvider()
model = OpenAIChatModel("gpt-4o-mini", provider=provider)
agent = MindtraceAgent(model=model, name="openai_agent")
```

### Ollama

```python
from mindtrace.agents import MindtraceAgent, OpenAIChatModel, OllamaProvider


provider = OllamaProvider(base_url="http://localhost:11434/v1")
model = OpenAIChatModel("llama3.2", provider=provider)
agent = MindtraceAgent(model=model, name="local_agent")
```

### Gemini

```python
from mindtrace.agents import MindtraceAgent, OpenAIChatModel, GeminiProvider


provider = GeminiProvider()
model = OpenAIChatModel("gemini-2.0-flash", provider=provider)
agent = MindtraceAgent(model=model, name="gemini_agent")
```

## Tools and RunContext

Tools are Python functions that the model can call. Parameters and docstrings are used to build the schema and description exposed to the model.

```python
import asyncio

from mindtrace.agents import MindtraceAgent, OpenAIChatModel, OpenAIProvider, RunContext, Tool


def get_weather(ctx: RunContext[None], city: str) -> str:
    """Get the current weather for a city."""
    return f"Weather in {city}: Sunny, 22°C"


provider = OpenAIProvider()
model = OpenAIChatModel("gpt-4o-mini", provider=provider)
agent = MindtraceAgent(model=model, tools=[Tool(get_weather)])

result = asyncio.run(agent.run("What's the weather in Paris?"))
```

`RunContext` is injected into tools when needed. It can carry:

- `deps` — your application dependencies
- `step` — the current agent iteration
- retry and tool-execution context

### Tool dependencies

```python
from dataclasses import dataclass

from mindtrace.agents import RunContext


@dataclass
class AppDeps:
    db_url: str


def lookup_user(ctx: RunContext[AppDeps], user_id: str) -> dict:
    """Look up a user by ID."""
    return {"id": user_id, "db": ctx.deps.db_url}
```

## Toolsets

Toolsets are the main way to organize and expose tools to an agent.

### FunctionToolset

Use `FunctionToolset` for Python tools you want to manage directly.

```python
from mindtrace.agents import MindtraceAgent, Tool
from mindtrace.agents.toolsets import FunctionToolset


def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b


toolset = FunctionToolset(max_retries=2)
toolset.add_tool(Tool(add))

agent = MindtraceAgent(model=model, toolset=toolset)
```

### CompoundToolset

Use `CompoundToolset` to merge multiple toolsets into one.

```python
from mindtrace.agents import MindtraceAgent
from mindtrace.agents.toolsets import CompoundToolset, FunctionToolset, MCPToolset


agent = MindtraceAgent(
    model=model,
    toolset=CompoundToolset(
        MCPToolset.from_http("http://localhost:8001/mcp-server/mcp/"),
        FunctionToolset(),
    ),
)
```

### MCPToolset

MCP (Model Context Protocol) is a standard way to expose application functionality as structured tools for AI clients. `MCPToolset` lets a `MindtraceAgent` use tools from any compatible remote MCP server.

Requires the MCP extra:

```bash
pip install 'mindtrace-agents[mcp]'
```

Examples:

```python
from mindtrace.agents.toolsets import MCPToolset


# HTTP (default for Mindtrace services)
ts = MCPToolset.from_http("http://localhost:8001/mcp-server/mcp/")

# SSE
ts = MCPToolset.from_sse("http://localhost:9000/sse")

# stdio
ts = MCPToolset.from_stdio(["npx", "-y", "@modelcontextprotocol/server-filesystem", "/tmp"])
```

To avoid tool name collisions when combining multiple MCP sources, use `prefix`:

```python
ts = MCPToolset.from_http("http://localhost:8002/mcp/", prefix="db")
# tools become db__query, db__list_tables, ...
```

## Filtering Tools

Toolsets can be filtered so the model sees only the tools you want to expose.

```python
# Allow only selected tools
toolset.include("search", "summarise")

# Exclude one tool
toolset.exclude("drop_table")

# Glob patterns
toolset.include_pattern("read_*", "list_*")
toolset.exclude_pattern("admin_*")
```

You can also compose filters explicitly:

```python
from mindtrace.agents.toolsets import ToolFilter


f = ToolFilter.include_pattern("read_*") & ~ToolFilter.include("read_credentials")
toolset.with_filter(f)
```

## Lifecycle Callbacks

`AgentCallbacks` lets you intercept key lifecycle points around model and tool execution.

```python
from mindtrace.agents import AgentCallbacks, MindtraceAgent


def log_before_llm(messages, model_settings):
    print(f"Sending {len(messages)} messages to LLM")
    return None


async def log_after_tool(tool_name, args, result, ctx):
    print(f"Tool {tool_name!r} returned: {result}")
    return None


callbacks = AgentCallbacks(
    before_llm_call=log_before_llm,
    after_tool_call=log_after_tool,
)

agent = MindtraceAgent(model=model, tools=[...], callbacks=callbacks)
```

Use callbacks when you want to:

- inspect or modify messages before the model call
- inspect or modify tool calls and tool results
- add tracing, metrics, or custom observability around the run loop

## Conversation History

History backends let an agent persist and reload conversation state across runs.

```python
import asyncio

from mindtrace.agents import InMemoryHistory, MindtraceAgent


history = InMemoryHistory()
agent = MindtraceAgent(
    model=model,
    history=history,
    system_prompt="You are a helpful assistant.",
)

reply1 = asyncio.run(agent.run("My name is Alice.", session_id="user-123"))
reply2 = asyncio.run(agent.run("What's my name?", session_id="user-123"))
```

For a custom backend, implement `AbstractHistoryStrategy`.

## Streaming and Iteration

If you want more than a single final response, the agents package gives you two good options.

### Streaming events

Use `run_stream_events()` when you want token deltas, tool results, and the final result as events.

```python
import asyncio

from mindtrace.agents import AgentRunResultEvent, PartDeltaEvent, PartStartEvent, ToolResultEvent


async def stream_example():
    async for event in agent.run_stream_events("Tell me a joke", session_id="s1"):
        if isinstance(event, PartStartEvent) and event.part_kind == "text":
            print("\n[Text started]")
        elif isinstance(event, PartDeltaEvent) and hasattr(event.delta, "content_delta"):
            print(event.delta.content_delta, end="", flush=True)
        elif isinstance(event, ToolResultEvent):
            print(f"\n[Tool result: {event.content}]")
        elif isinstance(event, AgentRunResultEvent):
            print(f"\n[Done: {event.result.output}]")


asyncio.run(stream_example())
```

### Step-by-step iteration

Use `iter()` when you want structured control over the execution loop itself.

```python
async def iterate_example():
    async with agent.iter("What's 15% of 240?") as steps:
        async for step in steps:
            if step["step"] == "model_response":
                print(step["text"])
            elif step["step"] == "tool_result":
                print(step["tool_name"], step["result"])
            elif step["step"] == "complete":
                print(step["result"])
```

## WrapperAgent

Use `WrapperAgent` when you want to add cross-cutting behavior around an existing agent without modifying the original class.

```python
import asyncio
import time

from mindtrace.agents import WrapperAgent


class TimedAgent(WrapperAgent):
    async def run(self, input_data, *, deps=None, **kwargs):
        start = time.monotonic()
        result = await super().run(input_data, deps=deps, **kwargs)
        self.logger.info(f"Run took {time.monotonic() - start:.2f}s")
        return result


timed = TimedAgent(agent)
result = asyncio.run(timed.run("Hello"))
```

## Multi-Agent Composition

Agents are first-class tools. You can pass one agent into another agent’s `tools=[]`, and the framework converts it automatically.

```python
researcher = MindtraceAgent(
    model=model,
    name="researcher",
    description="Research a topic and return facts",
)

writer = MindtraceAgent(
    model=model,
    name="writer",
    description="Write a structured report from given facts",
)

orchestrator = MindtraceAgent(
    model=model,
    tools=[researcher, writer],
)
```

When using an agent as a tool, `description` matters because that is what the parent model sees when deciding whether to call it.

### HandoffPart

`HandoffPart` marks an explicit agent-to-agent handoff boundary in message history.

```python
from mindtrace.agents import HandoffPart


part = HandoffPart(
    from_agent="orchestrator",
    to_agent="writer",
    summary="Researcher found: sea levels rose 20cm since 1980",
)
```

## Agent Memory

`MemoryToolset` exposes persistent memory as agent-callable tools. The agent can decide what to save, recall, search, or forget.

```python
from mindtrace.agents import JsonFileStore, MemoryToolset, MindtraceAgent
from mindtrace.agents.toolsets import CompoundToolset, FunctionToolset


memory = JsonFileStore("./agent_memory.json")

agent = MindtraceAgent(
    model=model,
    toolset=CompoundToolset(
        FunctionToolset(),
        MemoryToolset(memory, namespace="user_123"),
    ),
)
```

Exposed memory tools include:

- `save_memory`
- `recall_memory`
- `search_memory`
- `forget_memory`
- `list_memories`

### Memory backends

- `InMemoryStore` — in-memory only
- `JsonFileStore` — local JSON persistence

Implement `AbstractMemoryStore` if you want Redis, vector DBs, or other storage systems.

Optional extras:

```bash
pip install 'mindtrace-agents[memory-redis]'
pip install 'mindtrace-agents[memory-vector]'
```

## Distributed Execution

For larger deployments, agent execution can be routed through a task queue.

### LocalTaskQueue

Use `LocalTaskQueue` for single-process orchestration.

```python
from mindtrace.agents import AgentTask, LocalTaskQueue


queue = LocalTaskQueue()
queue.register(researcher)

# submit/get_result are async; shown here as the key flow
# task_id = await queue.submit(AgentTask(...))
# result = await queue.get_result(task_id)
```

### DistributedAgent

`DistributedAgent` wraps an agent and routes `run()` through a queue, while keeping the same high-level API.

```python
from mindtrace.agents import DistributedAgent


distributed_researcher = DistributedAgent(researcher, task_queue=queue)
# result = await distributed_researcher.run("Research topic")
```

### RabbitMQ

Install the RabbitMQ extra when you want multi-worker execution:

```bash
pip install 'mindtrace-agents[distributed-rabbitmq]'
```

Caller side:

```python
from mindtrace.agents.execution.rabbitmq import RabbitMQTaskQueue


queue = RabbitMQTaskQueue(url="amqp://guest:guest@localhost/")
distributed = DistributedAgent(researcher, task_queue=queue)
```

Worker side:

```python
queue = RabbitMQTaskQueue(url="amqp://guest:guest@localhost/")
# await queue.serve(researcher)
```

## Sync Usage

If you do not want to manage the event loop directly, use `run_sync()`:

```python
result = agent.run_sync("What is the capital of France?")
```

## Logging and Config

Agents, models, and providers inherit from Mindtrace base classes and automatically receive:

- `self.logger`
- `self.config`

```python
agent.logger.info("Starting run", session_id="abc")
```

## Examples

See these examples and related docs in the repo for more end-to-end reference:

- [Agents README quick-start examples](README.md)
- [MCP toolset examples in this README](README.md#mcp-toolset)
- [Memory toolset examples in this README](README.md#agent-memory)
- [Distributed execution examples in this README](README.md#distributed-execution)

## Testing

If you are working in the full Mindtrace repo, run tests for this module specifically:

```bash
git clone https://github.com/Mindtrace/mindtrace.git && cd mindtrace
uv sync --dev --all-extras
```

```bash
# Run the agents test suite
ds test: agents

# Run only unit tests for agents
ds test: --unit agents
```

## Practical Notes and Caveats

- Providers and models are separate concepts: providers handle backend connectivity, models handle the request/response interface.
- Tool docstrings and descriptions matter because the model sees them when deciding which tools to call.
- When using an agent as a tool, make sure it has a clear `description`.
- Distributed execution requires serializable task payloads; avoid passing live in-memory objects through distributed queues.
- MCP, RabbitMQ, and some memory backends require optional extras.
- `run()` is the simplest API, but streaming and iteration provide much better observability for debugging and UX.

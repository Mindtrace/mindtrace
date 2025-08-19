### MCPAgent usage
### Contents
- **Agent Run modes**
  - [Single turn with `run`](#single-turn-with-run)
  - [Persistent session with `open_agent`](#persistent-session-with-open_agent)
- **Agent Graphs**
  - [Using AgentGraph in three ways](#using-agentgraph-in-three-ways)
    - [Override example](#override-example)
    - [Factory example](#factory-example)
    - [Plugin example](#plugin-example)

This guide shows how to use `run` and `open_agent` with the sample `CalculatorService` implemented in `mindtrace/services/mindtrace/services/sample/calculator_mcp.py`.

Prereqs:

 -  The below code samples can be run via sample scripts available in `mindtrace/samples/services/agents/calculator`
 -  Use `docker compose up -d` command to setup Ollama service at port: "11434" before running the scripts

---

#### Single turn with `run`
For stateless requests—where conversation history and tool state do not need to be preserved across turns—you can use the agent’s run method.
```python
import asyncio

from mindtrace.services.agents.langraph.agent import MCPAgent
from mindtrace.services.agents.langraph.config import AgentConfig
from mindtrace.services.sample.calculator_mcp import CalculatorService


async def main():
    agent = MCPAgent(CalculatorService, AgentConfig())
    async for step in agent.run("thread-1", user_input="Add 2 and 3, then multiply by 4"):
        step["messages"][-1].pretty_print()


if __name__ == "__main__":
    asyncio.run(main())
```

What happens:
- Opens an MCP session, loads calculator tools
- Builds the agent graph
- Streams results and closes the session

---

#### Persistent session with `open_agent`
For multi-turn, stateful sessions, persistent tool context.
```python
import asyncio

from mindtrace.services.agents.langraph.agent import MCPAgent
from mindtrace.services.agents.langraph.config import AgentConfig
from mindtrace.services.sample.calculator_mcp import CalculatorService


async def main():
    agent = MCPAgent(CalculatorService, AgentConfig())
    async with agent.open_agent("thread-1") as (compiled, cfg):
        # turn 1
        msgs = [{"role": "user", "content": "multiply 2, 3, 4"}]
        async for step in compiled.astream(msgs, cfg):
            step["messages"][-1].pretty_print()

        # turn 2 (same session)
        msgs = [{"role": "user", "content": "add 100,20"}]
        async for step in compiled.astream(msgs, cfg):
            step["messages"][-1].pretty_print()

if __name__ == "__main__":
    asyncio.run(main())
```

What happens:
- Opens the MCP session once
- Builds the agent once
- Streams multiple turns without reconnecting

---

### Using AgentGraph in three ways
- Option 1 — Factory method: Build a custom graph end-to-end (primer → LLM → tools loop → summarize). Best when you want full control of flow.
- Option 2 — Override: Subclass the base graph and override nodes or the default build.
- Option 3 — Plugin: Inject or modify nodes/edges without replacing the whole graph.

### Override example

Example code (`samples/services/agents/calculator/agent_override_llm.py`) shows an override that replaces the base graph with an LLM‑only flow (no tool execution):
- Nodes: `greet → list_tools → goodbye`
- `list_tools` informs the user which tools are available (names only), but does not invoke them.

How this differs from the base graph:
- **Base graph**: LLM may emit tool calls; `tools` executes and loops back to LLM until no more calls.
- **Override**: Replaces that behavior entirely with a simple, linear LLM chat; no tool loop, no tool execution.

### Factory example:

Example code (`samples/services/agents/calculator/agent_factory_llm.py`) builds a custom graph with a summarizer step:
- Primer: injects guidance so the LLM plans tool use (e.g., add then divide) correctly.
- LLM: emits tool calls (calc_add, calc_divide, etc.) as needed.
- Tools: executes tool calls and loops back to the LLM for multi-step plans with retry-on-error logic.
- Summarize: final LLM-only node (no tools) to produce a concise, user-friendly answer.

### Plugin example:

Example code (`samples/services/agents/calculator/agent_plugin_llm.py`) demonstrates a minimal plugin that extends the base graph without replacing it:
- Adds a single `note` node after the base `tools` node.
- Wires `tools -> note` and sets `note` as the terminal node.

How this differs from the base graph:
- **Base graph**: `llm` emits tool calls; `tools` executes them and loops back to `llm` until no more tool calls, then ends.
- **With plugin**: After the final `tools` execution, control flows to `note` for a small post-processing step (e.g., appending a message), then ends. All other behavior remains unchanged.


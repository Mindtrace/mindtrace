import asyncio

from langchain_core.messages import HumanMessage
from langgraph.graph import MessagesState

from mindtrace.services.agents.langraph.agent import MCPAgent
from mindtrace.services.agents.langraph.config import AgentConfig
from mindtrace.services.agents.langraph.builder import MCPAgentGraph
from mindtrace.services.agents.langraph.graph.types import GraphBuilder, GraphContext
from mindtrace.services.sample.calculator_mcp import CalculatorService


class CalculatorOverrideLLM(MCPAgentGraph):
    """Override graph to an LLM-only friendly chat: greet then goodbye (no tools)."""

    def build_default(self, ctx: GraphContext):
        b = GraphBuilder(MessagesState)

        def greet(state: MessagesState):
            runnable = ctx.llm_provider.with_tools([], tool_choice="none")
            prompt = (
                "Greet the user briefly and warmly in one sentence. "
                "If a prior user message exists, acknowledge it politely."
            )
            ai = runnable.invoke(state["messages"] + [HumanMessage(content=prompt)])
            return {"messages": [ai]}

        def goodbye(state: MessagesState):
            runnable = ctx.llm_provider.with_tools([], tool_choice="none")
            prompt = "Say goodbye in one short friendly sentence."
            ai = runnable.invoke(state["messages"] + [HumanMessage(content=prompt)])
            return {"messages": [ai]}

        def list_tools(state: MessagesState):
            tool_names = ", ".join(sorted(getattr(t, "name", "") for t in ctx.tools)) or "(no tools)"
            runnable = ctx.llm_provider.with_tools([], tool_choice="none")
            prompt = f"Inform the user of available tools in one short sentence: {tool_names}."
            ai = runnable.invoke(state["messages"] + [HumanMessage(content=prompt)])
            return {"messages": [ai]}

        b.add_node("greet", greet)
        b.add_node("list_tools", list_tools)
        b.add_node("goodbye", goodbye)
        b.set_linear(["greet", "list_tools", "goodbye"]).set_entry("greet").set_terminal("goodbye")
        return b


async def main():
    agent = MCPAgent(CalculatorService, AgentConfig(), agent_graph=CalculatorOverrideLLM)
    async for step in agent.run("thread-override-llm", user_input="hello there"):
        step["messages"][-1].pretty_print()


if __name__ == "__main__":
    asyncio.run(main())


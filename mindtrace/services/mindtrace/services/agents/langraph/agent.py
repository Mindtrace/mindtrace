import asyncio
from typing import Any, AsyncIterable, Dict, List, Optional
import uuid

from ..base import MindtraceAgent
from .builder import MCPAgentGraph
from .config import OllamaAgentConfig as AgentConfig
from .graph.types import GraphContext, GraphFactory, GraphPlugin
from .llm import LLMProvider, OllamaProvider
from .mcp_tools import MCPToolSession
from .tool_exec import ToolExecutor


class MCPAgent(MindtraceAgent):
    """High-level agent orchestrator for MCP-backed tool-augmented LLMs.

    This class wires together:
    - An MCP tool session
    - A pluggable LLM provider (LangChain Runnable via with_tools)
    - A pluggable LangGraph graph (factory/plugins/subclass hooks)
    """

    def __init__(
        self,
        agent_config: AgentConfig | None = None,
        *,
        factory: GraphFactory | None = None,
        plugins: list[GraphPlugin] | None = None,
        agent_graph: type[MCPAgentGraph] = MCPAgentGraph,
        llm_provider: LLMProvider | None = None,
    ):
        super().__init__(agent_config)
        if agent_config is None:
            raise ValueError("config must be provided")

        self.agent_config = agent_config
        # Setup MCP tool session: prefer explicit client, then agent_config.mcp_client, then agent_config.mcp_url
        if getattr(self.agent_config, "mcp_client", None) is not None:
            self._session = MCPToolSession(client=self.agent_config.mcp_client)
        elif self.agent_config.mcp_url:
            self._session = MCPToolSession(url=self.agent_config.mcp_url)
        else:
            raise ValueError("Provide one of:`agent_config.mcp_client`, or `agent_config.mcp_url`.")
        self._llm_provider = llm_provider or OllamaProvider(agent_config.model, agent_config.base_url)
        self._executor = ToolExecutor()
        self._agent_graph = agent_graph
        self._factory = factory
        self._plugins = plugins or []
        # Persistent session state
        self._thread_id: Optional[str] = None
        self._ctx: Optional[GraphContext] = None
        self._compiled_agent = None
        self._cfg: Optional[Dict[str, Any]] = None
        self._session_acm = None
        self._lifecycle_lock = asyncio.Lock()

    async def start(self, thread_id: str | int):
        """Open MCP session once and compile the agent for this thread.

        If already started for the same thread, this is a no-op. If started for a
        different thread, it will close and reopen for the new thread.
        """
        async with self._lifecycle_lock:
            if self._session_acm is not None and self._thread_id == thread_id and self._compiled_agent is not None:
                return
            if self._session_acm is not None and self._thread_id != thread_id:
                # Avoid deadlock: close without re-acquiring the same lock
                await self.close(_already_locked=True)

            self._thread_id = str(thread_id)
            self._session_acm = self._session.open()
            try:
                await self._session_acm.__aenter__()
            except Exception:
                # Reset state on failure to enter session
                self._session_acm = None
                self._thread_id = None
                raise

            self._ctx = GraphContext(
                tools=self._session.tools,
                tools_by_name=self._session.tools_by_name,
                config=self.agent_config,
                llm_provider=self._llm_provider,
                executor=self._executor,
            )
            agent = self._build_agent(self._ctx)
            self._cfg = {"configurable": {"thread_id": thread_id}}
            agent.build(self._ctx)
            self._compiled_agent = agent

    async def close(self, *, _already_locked: bool = False):
        """Close the persistent MCP session and clear compiled agent state.

        If `_already_locked` is True, assumes the lifecycle lock is already held.
        """
        if _already_locked:
            if self._session_acm is not None:
                try:
                    await self._session_acm.__aexit__(None, None, None)
                finally:
                    self._session_acm = None
                    self._compiled_agent = None
                    self._ctx = None
                    self._cfg = None
                    self._thread_id = None
            return
        async with self._lifecycle_lock:
            await self.close(_already_locked=True)

    async def astream(
        self,
        messages: List[Dict[str, Any]],
        *,
        context: Optional[Dict[str, Any]] = None,
    ) -> AsyncIterable[Dict[str, Any]]:
        """Stream LangGraph values wrapped in a framework-agnostic event envelope.

        Reads thread_id from self._cfg if present; otherwise generates a UUID and initializes.
        """
        thread_id: Optional[str] = None
        if isinstance(self._cfg, dict):
            cfg_conf = self._cfg.get("configurable") or {}
            if isinstance(cfg_conf, dict):
                thread_id = cfg_conf.get("thread_id")

        if not thread_id:
            thread_id = uuid.uuid4().hex
            await self.start(thread_id)

        yield {"event": "status", "data": {"stage": "started", "thread_id": thread_id}}
        async for step in self._compiled_agent.astream(messages, self._cfg, stream_mode="values"):
            yield {"event": "message", "data": step}
        yield {"event": "status", "data": {"stage": "completed", "thread_id": thread_id}}

    def _build_agent(self, ctx: GraphContext):
        """Build the concrete `AgentGraphBase` for this session.

        The returned agent wires the configured LLM provider and tool executor into the
        abstract hooks `llm_with_tools` and `run_tools`.
        """
        provider = ctx.llm_provider
        executor = ctx.executor
        config = ctx.config
        tools = ctx.tools
        tools_by_name = ctx.tools_by_name
        factory = self._factory
        plugins = self._plugins
        agent_graph = self._agent_graph

        class _Concrete(agent_graph):
            def __init__(self_inner):
                super().__init__(factory=factory, plugins=plugins)

            def system_prompt(self_inner):
                return getattr(config, "system_prompt", None) or ""

            def llm_with_tools(self_inner):
                return provider.with_tools(tools, tool_choice=config.tool_choice)

            async def run_tools(self_inner, calls):
                return await executor.execute(calls, tools_by_name)

        return _Concrete()

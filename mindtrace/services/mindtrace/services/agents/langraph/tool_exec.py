import json

from langchain_core.messages import ToolMessage

from mindtrace.core import Mindtrace


class ToolExecutor(Mindtrace):
    """Executes tool calls and converts results into ToolMessages.

    Example:
        executor = ToolExecutor()
        msgs = await executor.execute(ai_message.tool_calls, tools_by_name)
    """

    async def execute(self, tool_calls, tools_by_name, *, raise_on_error: bool = True):
        """Execute each call using tools_by_name and return ToolMessage list.

        If `raise_on_error` is False, convert errors into ToolMessages instead of raising.
        Useful for demos or custom graphs that prefer to continue streaming.
        """
        messages = []
        for call in tool_calls:
            name = call["name"]
            args = call["args"]
            try:
                result = await tools_by_name[name].ainvoke(args)
                try:
                    content = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, default=str)
                except Exception:
                    content = str(result)
            except Exception as error:
                if raise_on_error:
                    raise
                content = f"Tool '{name}' failed: {error}"
            messages.append(ToolMessage(content=content, tool_call_id=call.get("id", name)))
        return messages

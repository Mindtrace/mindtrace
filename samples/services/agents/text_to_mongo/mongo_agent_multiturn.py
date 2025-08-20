#!/usr/bin/env python3
"""Interactive CLI agent with multi-turn conversations using MCPLangGraphAgent.

Run:
    python mongo_agent_multiturn.py

Commands:
    /exit or /quit: exit the CLI
    /reset: clear the conversation history
    /help: show commands
"""

import asyncio

from langchain_core.messages import HumanMessage, AIMessage
from langchain_ollama.chat_models import ChatOllama

from mindtrace.services.sample.mongo_mcp import MongoService
from mindtrace.services.agents.langraph import AgentConfig, MCPAgent
from mindtrace.services.agents.langraph.graph import GraphBuilder, GraphContext
from mindtrace.services.agents.langraph.mcp_tools import MCPToolSession

async def main():
    # MongoDB connection URL - you can modify this as needed
    db_url = "mongodb://admin:secret123@localhost:27017"
    
    mcp_client = MongoService.mcp.launch(
                                                    host="localhost",
                                                    port=8000,
                                                    wait_for_launch=True,
                                                    timeout=10,
                                                    db_url=db_url,
                                                )
    mcp_session = MCPToolSession(client=mcp_client)
    
    agent = MCPAgent(
        mcp_session=mcp_session,
        config=AgentConfig(
            model="qwen3:32b",
            base_url="http://localhost:11434",
            tool_choice="any",
            system_prompt="""You are a friendly MongoDB assistant created by Mindtrace for the "demo" database with 3 collections: `welds`, `image`, and `parts`.
                                Use:
                                - `mongo_find` for basic queries
                                - `mongo_count` for counting
                                - `mongo_aggregate` for pipelines (joins, group, sort)

                                Schema Summary:
                                - welds: name, camera_id, defect, image_id
                                - image: image_id, camera_id, analytic_id
                                - parts: serial_number, analytic_id

                                Relations:
                                - welds.image_id = image.image_id
                                - image.analytic_id = parts.analytic_id
                                Reply to any user greeting with a friendly message, if you are not able to answer the question, say you are not sure.
                                
                                Database structure (agent guidance):
                                - Collection: welds
                                - name: e.g., "IBWA1", "IBWA2"
                                - camera_id: e.g., "cam1" to "cam12"
                                - defect: e.g., "burnthrough", "missing", "cold_weld", "spatter", "Healthy"
                                - image_id: e.g., "image1" to "image44"
                                - Collection: image
                                - camera_id: same as in welds
                                - image_id: same as in welds
                                - analytic_id: e.g., [4567, 4568, 4569, 4570]
                                - Collection: parts
                                - serial_number: e.g., "12345", "12346"
                                - analytic_id: e.g., [4567, 4568, 4569, 4570]
                                Relationships:
                                - welds.image_id == image.image_id
                                - image.analytic_id == parts.analytic_id
                            """,
        ),
    )

    print("=== Mindtrace CLI Agent (multi-turn) ===")
    print("Type /help for commands.\n")

    thread_id = "cli-mongo"
    conversation = []  # list of LangChain messages

    async def ainput(prompt: str) -> str:
        return await asyncio.to_thread(input, prompt)

    # Keep a persistent MCP session and compiled agent for the whole CLI session
    async with agent.open_agent(thread_id) as (compiled_agent, agent_cfg):
        while True:
            user_text = await ainput("You: ")
            if not user_text:
                continue
            cmd = user_text.strip().lower()
            if cmd in {"/exit", "/quit"}:
                print("Goodbye!")
                break
            if cmd == "/reset":
                conversation.clear()
                print("History cleared.")
                continue
            if cmd == "/help":
                print("/exit or /quit: exit; /reset: clear history; /help: show commands")
                continue

            # Append user turn to conversation
            conversation.append(HumanMessage(content=user_text))

            # Stream a single turn using full conversation context
            prev_len = len(conversation)
            latest_state_messages = conversation
            # Use the open agent to avoid re-launching MCP every turn
            try:
                async for step in compiled_agent.astream(conversation, agent_cfg, stream_mode="values"):
                    current = step["messages"]
                    # Print only the new messages since the start of this turn
                    new_msgs = current[prev_len:]
                    for m in new_msgs:
                        try:
                            m.pretty_print()
                        except Exception:
                            print(f"Assistant: {getattr(m, 'content', str(m))}")
                    latest_state_messages = current
            except Exception as e:
                print(f"Assistant: Encountered an error while processing your request: {e}")

            # Persist full state as the new conversation for next turn
            conversation = list(latest_state_messages)


if __name__ == "__main__":
    asyncio.run(main())


    # Sample Queries
    # count number of welds in welds collection
    # can you give me defective weld count
    # can you give me summary of defective welds
    # can you give me summary of welds with defect burnthrough
    # can you use mindtrace tools to give me summary of defective welds
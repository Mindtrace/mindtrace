## MongoDB Sample Agent

In this section, we demonstrate how to use the `MCPAgent` from Mindtrace to build a multi-turn conversational agent that interfaces with a MongoDB database using locally hosted large language models (LLMs). The agent can understand natural language queries, translate them into MongoDB operations, and return structured results conversationally.

---
## Prerequisites Before the Hands-On Session
### Launch Required Services with Docker

Run the following command to start the services in the background:

``` bash
docker compose up -d
```
This will launch two key containers: 
- **Ollama**: An open-source LLM runtime 
- **MongoDB**: A local database to store mock data for querying. If you have a existing database setup, you can skip the mongodb setup.

By default, the setup pulls the `qwen:32b` model. This model has been
selected based on Qwen model performances on the [Berkeley Function-Calling
Leaderboard](https://gorilla.cs.berkeley.edu/leaderboard.html) in general.

-   **Size Warning**: The Qwen 32B model requires approximately **20
    GB** of space.
-   **Model Selection Tip**: If you prefer a smaller model, you may
    switch to a lightweight version. However, **context window size
    is critical** for multi-turn reasoning in our use case, so choose
    the model accordingly.


We've included a mock dataset for demonstration purposes. It will
automatically be created using a `seed.js` script, and contains: - Weld
information - Associated images - Corresponding parts

This schema is used to simulate industrial inspection data and supports
natural language querying.


To confirm the Qwen model has been pulled successfully, run the
following command:

``` bash
curl http://localhost:11434/api/tags
```

If the model appears in the response, your setup is complete.

-----

## Run the agent

```bash
python mongo_agent_multiturn.py
```
Try following Queries:
- Any Greetings (`hi`, `hello`)
- "count number of welds in welds collection"
- "can you give me defective weld count"
- "summary of welds with defect burnthrough"

Tips: `/help` for commands, `/reset` clears history, `/exit` quits.


## Code Overview

This sample demonstrates the Model Context Protocol (MCP) pattern. The LLM does not connect to MongoDB directly. Instead, it interacts with MCP tools exposed by the MongoService, a class that inherits from the Mindtrace `Service` base. The agent decides when to call which tool and how to use the results to answer your question.

### Remote MCP service (Mongo tools)

A sample remote MCP server is implemented in the codebase at the module path `mindtrace.services.sample.mongo_mcp`. It registers three tools:
- `mongo_find(FindInput) -> FindOutput`
- `mongo_aggregate(AggregateInput) -> AggregateOutput`
- `mongo_count(CountInput) -> CountOutput`

We launch the MCP server in-process, passing the MongoDB connection URL, and obtain an MCPClient instance. This client can be used to create an MCPToolSession, which allows the agent to discover and invoke tools exposed by the MongoService.

```python
mcp_client = MongoService.mcp.launch(
    host="localhost", port=8000, wait_for_launch=True, timeout=10,
    db_url="mongodb://admin:secret123@localhost:27017",
)
```
### MCPToolSession
The MCPToolSession is an async context manager. When opened, it loads tools for the provided mcp_client via the MCP protocol and populates `session.tools` and `session.tools_by_name`. When the session is closed, it gracefully tears down the connection.
```
mcp_session = MCPToolSession(client=mcp_client)
```
### The Agent Config
```python
AgentConfig(
            model="qwen3:32b",
            base_url="http://localhost:11434",
            tool_choice="any",
            system_prompt=""" """,
        ),
```
This AgentConfig is passed to both the LLM provider (Ollama) and the agent execution graph.
Combined with the tools loaded by MCPToolSession, it enables tool-augmented reasoning. When the LLM decides to use a tool (e.g., to answer a database query), the agent:

Looks up the correct tool in tools_by_name

Executes it with the appropriate arguments

Feeds the results back into the ongoing conversation










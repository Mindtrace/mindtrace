[![PyPI version](https://img.shields.io/pypi/v/mindtrace-agents)](https://pypi.org/project/mindtrace-agents/)
[![License](https://img.shields.io/pypi/l/mindtrace-agents)](https://github.com/mindtrace/mindtrace/blob/main/mindtrace/agents/LICENSE)
[![Downloads](https://static.pepy.tech/badge/mindtrace-agents)](https://pepy.tech/projects/mindtrace-agents)

# Mindtrace Agents

The foundational module for building and managing AI-powered agents in the Mindtrace ecosystem. This package provides a flexible framework for creating, discovering, and configuring agents that can interact with various services and data sources.

## Features

- **Agent Discovery**: Automatic discovery and registration of agents via a registry system
- **CLI Integration**: Built-in CLI commands for all registered agents
- **Flexible Configuration**: Environment-based and file-based configuration support
- **LLM Provider Support**: Works with multiple LLM providers (OpenAI, Ollama, Gemini, etc.)
- **Tool Integration**: Easy integration of tools and functions for agent capabilities
- **Versioning**: Agent versioning support for managing different agent versions

## Installation

```bash
# Install as standalone package
uv add mindtrace-agents

# Or with pip
pip install mindtrace-agents
```

## Agent Discovery

Agents are automatically discovered and registered when the package is imported. You can list all available agents using the CLI:

```bash
# List all registered agents
mindtrace agents --list

# Or get help for the agents command
mindtrace agents
```

The output will show all registered agents with their descriptions:

```
  - monitor: AI-powered log monitoring and analysis agent
```

Agents are registered using the `AgentRegistry` class, which stores agent metadata in a persistent registry. Each agent registration includes:

- **name**: Unique identifier for the agent
- **description**: Human-readable description
- **cli_module**: Python module path where the CLI class is located
- **cli_class**: Name of the CLI class
- **version**: Optional version string (defaults to auto-increment)

## How to Configure Agents

Agents are configured using environment variables or configuration files. The configuration follows a hierarchical structure:

### Configuration Structure

```json
{
  "MT_AGENTS": {
    "monitor": {
      "models": {
        "query_generator": {
          "provider": "ollama",
          "model_name": "llama3.1",
          "system_prompt": "You are a LogQL query generator..."
        },
        "log_analyzer": {
          "provider": "ollama",
          "model_name": "llama3.1",
          "system_prompt": "You are a professional log analysis assistant..."
        }
      }
    }
  },
  "MT_LLM_PROVIDERS": {
    "ollama": {
      "type": "ollama",
      "base_url": "http://localhost:11435",
      "default_model": "llama3.1"
    },
    "openai": {
      "type": "openai",
      "api_key": "${OPENAI_API_KEY}"
    },
    "gemini": {
      "type": "gemini",
      "api_key": "${GEMINI_API_KEY}"
    }
  }
}
```

### Configuration Methods

#### 1. Environment Variables

Set environment variables matching the field names exactly, using `__` (double underscore) as the nested delimiter:

```bash
export MT_AGENTS__MONITOR__MODELS__QUERY_GENERATOR__PROVIDER="ollama"
export MT_AGENTS__MONITOR__MODELS__QUERY_GENERATOR__MODEL_NAME="llama3.1"
export MT_LLM_PROVIDERS__OLLAMA__BASE_URL="http://localhost:11435"
```

#### 2. Configuration Files

Agents can load configuration from JSON files:

```bash
# Configure via CLI (saves to ~/.config/mindtrace/agents/monitor.json)
mindtrace agents monitor configure --config '{"LOKI_URL": "http://localhost:3100"}'
```

#### 3. Python Code

```python
from mindtrace.agents.monitor.agent import MonitorAgent

config = {
    "MT_AGENTS": {
        "monitor": {
            "models": {
                "query_generator": {
                    "provider": "ollama",
                    "model_name": "llama3.1"
                }
            }
        }
    },
    "MT_LLM_PROVIDERS": {
        "ollama": {
            "type": "ollama",
            "base_url": "http://localhost:11435"
        }
    }
}

agent = MonitorAgent(config_override=config)
```

## Agent Catalogue
### Monitor Agent

The Monitor Agent is an AI-powered log monitoring and analysis agent that converts natural language queries into LogQL queries for Loki and provides intelligent log analysis.

#### Features

- **Natural Language to LogQL**: Convert human queries into LogQL queries
- **Log Analysis**: Analyze logs and provide insights
- **Service Filtering**: Filter logs by service name
- **Structured Output**: Returns structured analysis results

#### Setup

For detailed setup instructions, see the [Monitor Agent Setup Guide](../../samples/agents/monitor_setup/logging/README.md).

The setup includes:
- **Logging Service**: Simulates realistic log patterns
- **Loki**: Log storage and indexing
- **Grafana**: Log visualization dashboard
- **Promtail**: Log collection agent

#### Example Queries

```bash
# Analyze errors
mindtrace agents monitor query -s LoggingService -q "analyze all errors"
```

#### Configuration

Configure the Monitor Agent with Loki URL and LLM providers:

```bash
mindtrace agents monitor configure --config '{
  "LOKI_URL": "http://localhost:3100",
  "MT_LLM_PROVIDERS": {
    "ollama": {
      "type": "ollama",
      "base_url": "http://localhost:11435",
      "default_model": "llama3.1"
    }
  }
}'
```

#### How It Works

1. **Service Logging to Loki**: Services write structured logs that are collected by Promtail and stored in Loki
2. **Natural Language Query**: User provides a natural language query
3. **LogQL Generation**: The agent converts the query to LogQL using an LLM
4. **Log Retrieval**: Logs are fetched from Loki using the generated LogQL query
5. **Analysis**: Another LLM analyzes the logs and provides insights
6. **Response**: Structured response with analysis and the LogQL query used

## Creating Custom Agents

To create a custom agent:

1. **Create an Agent Class**:
   ```python
   from mindtrace.agents.catalogue.agents import BaseAgent
   
   class MyAgent(BaseAgent):
       agent_name = "my_agent"
       description = "My custom agent"
       
       async def run(self, input: str, **kwargs) -> dict:
           # Your agent logic here
           return {"result": "..."}
   ```

2. **Create a CLI Class**:
   ```python
   from mindtrace.agents.catalogue.agents import BaseAgentCLI
   import click
   
   class MyAgentCLI(BaseAgentCLI):
       agent_class = MyAgent
       
       @classmethod
       def cli_group(cls) -> click.Group:
           @click.group()
           def my_agent():
               """My custom agent commands"""
               pass
           
           @my_agent.command()
           @click.option("--input", required=True)
           def run(input):
               agent = cls.agent_class()
               result = asyncio.run(agent.run(input))
               click.echo(result)
           
           return my_agent
   ```

3. **Register the Agent**:
   ```python
   from mindtrace.agents.catalogue.agents import AgentRegistry
   
   AgentRegistry.register(
       name="my_agent",
       description="My custom agent",
       cli_module="my_package.agents.my_agent",
       cli_class="MyAgentCLI",
       version="1.0.0"
   )
   ```


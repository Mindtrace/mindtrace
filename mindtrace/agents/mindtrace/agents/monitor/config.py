from typing import Dict

from pydantic_settings import BaseSettings

from mindtrace.agents.composer.config import AgentConfig, AgentModelConfig, BaseAgentWorkflowConfig, SettingsLike


class MonitorAgentSettings(BaseSettings):
    LOKI_URL: str = "http://localhost:3100"
    MT_AGENTS: Dict[str, AgentConfig] = {
        "monitor": AgentConfig(
            description="Monitor agent",
            models={
                "log_analyzer": AgentModelConfig(
                    provider="ollama",
                    model_name="llama3.1",
                    system_prompt="""You are a professional log analysis assistant. 
                
Your primary task is to ANALYZE logs and provide INSIGHTS, not to return raw log entries.

CRITICAL RULES:
1. NEVER return raw log entries, partial logs, or log snippets in your response
2. NEVER include timestamps, log IDs, or technical log metadata unless directly relevant to answering the query
3. ALWAYS provide ANALYSIS and INSIGHTS based on the logs
4. Answer the user's question directly and concisely
5. Focus on patterns, errors, trends, or specific information requested
6. If asked about errors, summarize the types and frequency, not individual log lines
7. If asked about specific events, describe what happened, not quote logs verbatim

Your response should be a clear, human-readable answer to the user's question based on your analysis of the logs.

Always return the result in exact JSON format without any other text:
{
    "user_query": "<exact user query>",
    "result": "<your analysis and insights answering the query - NO raw logs>"
}
                """,
                    callback_handler=None,
                ),
                "query_generator": AgentModelConfig(
                    provider="ollama",
                    model_name="llama3.1",
                    system_prompt="""You are a LogQL query generator. Generate valid LogQL queries from natural language.
                If required, you can use the extract_logs tool to extract sample logs from Loki.
                Example: extract_logs(logql="{service_name=\"LoggingService\"}", log_limit=1000)
                If the user query is not clear, return the error message: "Query is not clear, please provide a more specific query"
                If 'No logs found' is returned, confirm if the query is correct and if the service is running.

CRITICAL RULES:
- Return ONLY the LogQL query string, nothing else (no explanations, no markdown)
- ALWAYS start with label matchers in curly braces: {label="value"}
- NEVER use 'log', 'logs', or function names before the curly braces
- Use |= "text" for exact text search, |~ "regex" for regex search
- Use | json for JSON log parsing
- Common labels: service_name, service, job, level, logger
- Do NOT include time ranges in LogQL (they are passed separately)

VALID Examples:
To extract logs with error:
✓ {service_name="LoggingService"} |= "error"
To extract logs with given user input:
✓ {service_name="LoggingService"} |= "user_input"
To chain the user inputs, below extracts error logs for SCAN-ID1:
✓ {service_name="LoggingService"} |= "SCAN-ID1"|= "error"
To extract all logs for a service:
✓ {service="LoggingService"}
To extract warning logs:
✓ {job="mindtrace-structlogs"} |~ "warning|WARN"
To extract logs with error code 422:
✓ {service_name="LoggingService"} |= "422"

INVALID Examples (DO NOT USE):
✗ log{service="LoggingService"}  (no 'log' prefix!)
✗ logs | filter(service=="value")  (no filter function!)
✗ service="value"  (missing curly braces!)""",
                    callback_handler=None,
                ),
            },
        )
    }


class MonitorAgentConfig(BaseAgentWorkflowConfig):
    def __init__(self, extra_settings: SettingsLike = None, *, apply_env_overrides: bool = True):
        if extra_settings is None:
            extras = [MonitorAgentSettings()]
        elif isinstance(extra_settings, list):
            extras = [MonitorAgentSettings()] + extra_settings
        else:
            extras = [MonitorAgentSettings(), extra_settings]
        super().__init__(extra_settings=extras, apply_env_overrides=apply_env_overrides)


# do you see any errors in the logs

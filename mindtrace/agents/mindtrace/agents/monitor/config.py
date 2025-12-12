from pydantic import BaseModel
from pydantic_settings import BaseSettings
from typing import Dict
from mindtrace.agents.composer.config import BaseAgentWorkflowConfig, SettingsLike, AgentConfig, AgentModelConfig



class MonitorAgentSettings(BaseSettings):
    LOKI_URL: str = "http://localhost:3100"
    MT_AGENTS: Dict[str, AgentConfig] = {
        "monitor": AgentConfig(
            description="Monitor agent",
            models={
                "log_analyzer": AgentModelConfig(provider="ollama", 
                model_name="llama3.1", 
                system_prompt="""You are a professional log assistant. 
                Your task is to answer the human query for provided logs.
                You dont need to return the logs, rather return your insights in a concise manner.
                Always Return the result in exact JSON format without any other text:
                response = {
                    "user_query": "<exact user query>",
                    "result": "<result of the user query>"
                }
                """,
                callback_handler=None,),

                "query_generator": AgentModelConfig(provider="ollama", 
                model_name="llama3.1", 
                system_prompt="""You are a LogQL query generator. Generate valid LogQL queries from natural language.
                If required, you can use the extract_logs tool to extract sample logs from Loki.
                Example: extract_logs(logql="{service_name=\"EchoService\"}", log_limit=2)

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
✓ {service_name="EchoService"} |= "error"
To extract logs with given user input:
✓ {service_name="EchoService"} |= "user_input"
To chain the user inputs, below extracts error logs for SCAN-ID1:
✓ {service_name="MockPLCService"} |= "SCAN-ID1"|= "error"
To extract all logs for a service:
✓ {service="MockPLCService"}
To extract warning logs:
✓ {job="mindtrace-structlogs"} |~ "warning|WARN"
To extract logs with error code 422:
✓ {service_name="EchoService"} |= "422"

INVALID Examples (DO NOT USE):
✗ log{service="MockPLCService"}  (no 'log' prefix!)
✗ logs | filter(service=="value")  (no filter function!)
✗ service="value"  (missing curly braces!)""",callback_handler=None,),

            }
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
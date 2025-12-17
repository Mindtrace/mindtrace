import os
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import requests
from pydantic import BaseModel
from strands import tool

from mindtrace.agents.catalogue.agents import BaseAgent
from mindtrace.agents.monitor.config import MonitorAgentConfig


class LogAssistantResponse(BaseModel):
    user_query: str
    result: str


class MonitorAgent(BaseAgent):
    agent_name = "monitor"

    def __init__(self, config_override=None):
        super().__init__(config_override)
        self.config = MonitorAgentConfig(config_override)

        self.analyzer_model = self.get_model("log_analyzer")
        self.analyzer_agent = self.get_agent("log_analyzer", tools=[])

        self.query_generator_model = self.get_model("query_generator")
        self.query_generator_agent = self.get_agent("query_generator", tools=[self.extract_logs])

    def get_logql_from_response(self, response: str) -> str:
        response = response.strip()
        lines = response.split("\n")
        for line in lines:
            line = line.strip()
            if line.startswith("{") or "|=" in line or "|~" in line or "| json" in line:
                if line.startswith("{"):
                    end_idx = line.rfind("}")
                    if end_idx > 0:
                        logql = line[: end_idx + 1]
                        rest = line[end_idx + 1 :].strip()
                        if rest:
                            logql += " " + rest
                        return logql.strip()
                return line.strip()
        return response

    def send_loki_request(
        self, loki_url: str, logql: str, start_time: str, end_time: str, log_limit: int
    ) -> Dict[str, Any]:
        url = f"{loki_url}/loki/api/v1/query_range"
        params: Dict[str, Any] = {"query": logql, "start": start_time, "end": end_time, "limit": log_limit}
        response = requests.get(url, params=params, timeout=30)
        return response

    @tool
    def extract_logs(self, logql: str, log_limit=2) -> Dict[str, Any]:
        """Extract logs from Loki based on the LogQL query.

        Args:
            logql: The LogQL query string to extract logs from.
            log_limit: The number of logs to extract.

        Returns:
            Dictionary with:
            - success: bool - True if logs were extracted successfully
            - error: str - Error message (if success=False)
            - count: int - Number of logs found
            - logs: list - List of logs found
        """
        try:
            loki_url = self.config.get("LOKI_URL", "http://localhost:3100")

            # Set defaults: start = now - 7 days, end = now, limit = 10000
            now = datetime.now()
            end_time = str(int(now.timestamp() * 1_000_000_000))
            start_time = str(int((now - timedelta(days=7)).timestamp() * 1_000_000_000))
            response = self.send_loki_request(loki_url, logql, start_time, end_time, log_limit)
            response.raise_for_status()

            data = response.json()

            logs = []
            if "data" in data and "result" in data["data"]:
                for stream in data["data"]["result"]:
                    if "values" in stream:
                        for value in stream["values"]:
                            if len(value) >= 2:
                                logs.append(
                                    {"timestamp": value[0], "log": value[1], "labels": stream.get("stream", {})}
                                )

            if not logs:
                return {"success": False, "error": "No logs found", "count": 0, "logs": []}

            return {"success": True, "count": len(logs), "logs": logs}

        except Exception as e:
            return {"success": False, "error": str(e), "count": 0, "logs": []}

    def check_log_exists(self, logql: str) -> Dict[str, Any]:
        """ "
        Args:
            logql: The LogQL query string to check.

        Returns:
            Dictionary with:
            - success: bool - True if log exists
            - error: str - Error message (if success=False)
            - count: int - Number of logs found

        """

        res = self.extract_logs(logql)
        if res["success"]:
            return {"success": True, "count": res["count"]}
        else:
            return {"success": False, "error": res["error"]}

    async def run(self, query: str, time_window: Optional[str] = None) -> dict:
        prompt = f"Generate and validate a LogQL query for: {query}.Always if validation is successful, return the LogQL query only without any other text else error message"
        return self.planner_agent(prompt)

    async def query(self, query: str, service: str) -> dict:
        max_retries = 3

        res = self.check_log_exists(logql=f'{{service_name="{service}"}}')
        if not res["success"]:
            if res["error"] == "No logs found":
                return {
                    "AI_message": f"Logs for provided service: {service} not found for last 7 days in loki {self.config.get('LOKI_URL')}. Please Confirm the service name and if the service is running"
                }
            else:
                return {"AI_message": res["error"]}
        valid_logql = f'{{service_name="{service}"}}'
        prompt = f"For the service_name: {service}, generate a LogQL query: {query}.Return ONLY the LogQL query string.Do not add time ranges."
        # Suppress stdout/stderr to prevent unwanted output
        with open(os.devnull, "w") as devnull:
            with redirect_stdout(devnull), redirect_stderr(devnull):
                response = self.query_generator_agent(prompt)
        suggested_logql = self.get_logql_from_response(str(response))
        res = self.check_log_exists(logql=suggested_logql)
        if not res["success"]:
            # if res["error"] == "No logs found":
            #     return {"AI_message": f"Loki Query: {response} resulted in no logs, Would you like to try again with a different query?"}
            # else:
            for i in range(max_retries):
                prompt = f"Previous query failed with error: {res['error']}.Generate a corrected LogQL query for: {query}\n\nReturn ONLY the LogQL query string.Do not add time ranges."
                # Suppress stdout/stderr to prevent unwanted output
                with open(os.devnull, "w") as devnull:
                    with redirect_stdout(devnull), redirect_stderr(devnull):
                        response = self.query_generator_agent(prompt)
                        suggested_logql = self.get_logql_from_response(str(response))
                        res = self.check_log_exists(logql=suggested_logql)
                        if res["success"]:
                            valid_logql = suggested_logql
                            break
        else:
            valid_logql = suggested_logql

        if not res["success"]:
            return {
                "AI_message": "Unable to generate a valid LogQL query. Would you like provide a correct query?",
                "logql": suggested_logql,
            }
        logs = self.extract_logs(logql=valid_logql, log_limit=2000)
        if logs:
            with open(os.devnull, "w") as devnull:
                with redirect_stdout(devnull), redirect_stderr(devnull):
                    response = self.analyzer_agent.structured_output(
                        LogAssistantResponse,
                        prompt=f"create a summary for the human query: {query},analyze the service logs {logs}, ",
                    )
            return {
                "logql": valid_logql,
                "AI_message": str(response.result),
            }
        else:
            return {"AI_message": "Failed to extract logs for analysis.", "logql": valid_logql}


if __name__ == "__main__":
    import asyncio

    agent = MonitorAgent()
    result = asyncio.run(agent.query(query="analyze any errors in the logs", service="LoggingService"))

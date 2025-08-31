import sys
import time

from mindtrace.services.sample.calculator_mcp import CalculatorService
from mindtrace.services.agents.langraph.agent import MCPAgentService


def main():
    calc_host = "localhost"
    calc_port = 8000
    agent_host = "localhost"
    agent_port = 8080
    model = "qwen2.5:7b"
    ollama_base_url = "http://localhost:11434"

    calc_url = f"http://{calc_host}:{calc_port}"

    try:
        CalculatorService.launch(host=calc_host, port=calc_port, wait_for_launch=True, timeout=60)
        print(f"[launch] CalculatorService at {calc_url}")
    except Exception as e:
        print(f"[launch] CalculatorService may already be running: {e}", file=sys.stderr)

    try:
        MCPAgentService.launch(
            model=model,
            base_url=ollama_base_url,
            mcp_url=calc_url,
            host=agent_host,
            port=agent_port,
            wait_for_launch=True,
            timeout=60,
        )
        print(f"[launch] MCPAgentService at http://{agent_host}:{agent_port}")
    except Exception as e:
        print(f"[launch] MCPAgentService may already be running: {e}", file=sys.stderr)

    print("[launch] Services running. Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("[shutdown] Exiting launcher.")


if __name__ == "__main__":
    main() 
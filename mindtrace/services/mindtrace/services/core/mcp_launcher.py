import argparse
import json
import logging
from pathlib import Path

from mindtrace.core import instantiate_target, setup_logger

def main():
    parser = argparse.ArgumentParser(description="MINDTRACE MCP SERVER LAUNCHER")
    parser.add_argument(
        "-s", "--server_class",
        type=str,
        default="mindtrace.services.core.service.Service",
        help="Fully qualified class path of the MCP-compatible service to launch",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host to bind the MCP server",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port to bind the MCP server",
    )
    parser.add_argument(
        "--path",
        type=str,
        default="/rpc",
        help="RPC path to expose the MCP server (e.g., /mcp, /rpc)",
    )
    parser.add_argument(
        "--init-params",
        type=str,
        default="{}",
        help="JSON string of service initialization parameters (must include enable_mcp=True)",
    )
    args = parser.parse_args()

    init_params = json.loads(args.init_params)
    init_params["enable_mcp"] = True

    service = instantiate_target(args.server_class, **init_params)

    service.logger = setup_logger(
        name=service.unique_name,
        stream_level=logging.INFO,
        file_level=logging.DEBUG,
        log_dir=Path(service.config["MINDTRACE_LOGGER_DIR"]),
    )

    service.mcp.run(transport="http",host=args.host, port=args.port, path=args.path)


if __name__ == "__main__":
    main()
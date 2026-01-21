"""ToolService launcher."""

import argparse
import os
from typing import List, Optional, Set

from mindtrace.agents.server.tool_service import ToolService


def main():
    """Main launcher function."""
    parser = argparse.ArgumentParser(description="Launch ToolService")
    parser.add_argument("--host", default=os.getenv("TOOL_SERVICE_HOST", "0.0.0.0"), help="Service host")
    parser.add_argument("--port", type=int, default=int(os.getenv("TOOL_SERVICE_PORT", "8000")), help="Service port")
    parser.add_argument("--workers", type=int, default=1, help="Number of worker processes")
    parser.add_argument("--toolkits", type=str, required=True, help="Comma-separated list of toolkit names")
    parser.add_argument("--tags", type=str, default=None, help="Comma-separated list of tags to filter tools")
    parser.add_argument("--server-name", type=str, default=None, help="Server name for logging")

    args = parser.parse_args()

    # Parse toolkits
    toolkits: List[str] = [t.strip() for t in args.toolkits.split(",") if t.strip()]
    
    # Parse tags
    tags: Optional[Set[str]] = None
    if args.tags:
        tags = {t.strip() for t in args.tags.split(",") if t.strip()}

    # Launch the service (blocking to keep process alive)
    # This follows the hardware launcher pattern
    # Pass toolkits, tags, and server_name as kwargs so they're included in init_params
    # when the subprocess instantiates ToolService
    connection_manager = ToolService.launch(
        host=args.host,
        port=args.port,
        num_workers=args.workers,
        wait_for_launch=True,
        block=True,  # Block to keep the process alive (like hardware launchers)
        toolkits=toolkits,
        tags=tags,
        server_name=args.server_name,
    )

    return connection_manager


if __name__ == "__main__":
    main()

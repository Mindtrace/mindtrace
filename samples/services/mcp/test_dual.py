import argparse
from mindtrace.services import Service

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Launch Mindtrace Service as FastAPI or MCP server.")
    parser.add_argument(
        "--mode",
        choices=["fastapi", "mcp"],
        default="fastapi",
        help="Launch mode: 'fastapi' for FastAPI server, 'mcp' for MCP server."
    )
    parser.add_argument("--host", type=str, default="localhost", help="Host address.")
    parser.add_argument("--port", type=int, default=8000, help="Port number.")
    parser.add_argument("--path", type=str, default="/mcp", help="MCP path (for MCP mode only).")
    parser.add_argument("--block", action="store_true", help="Block process after launch.")
    args = parser.parse_args()

    if args.mode == "fastapi":
        print(f"Launching FastAPI server at {args.host}:{args.port}")
        Service.launch(host=args.host, port=args.port, block=args.block)
    elif args.mode == "mcp":
        print(f"Launching MCP server at {args.host}:{args.port}{args.path}")
        Service.launch_mcp(host=args.host, port=args.port, path=args.path, block=args.block) 
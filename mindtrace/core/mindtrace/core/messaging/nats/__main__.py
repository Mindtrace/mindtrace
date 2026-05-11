"""Minimal CLI for `NatsClient` — handy for ops smoke tests, not a load tester.

Usage:
    python -m mindtrace.core.messaging.nats publish <subject> <payload> [--json] [--file PATH]
    python -m mindtrace.core.messaging.nats subscribe <subject> [--count N]
    python -m mindtrace.core.messaging.nats request <subject> <payload> [--json] [--file PATH] [--timeout 2.0]

Reads `MINDTRACE_NATS__URLS` (and the other `MINDTRACE_NATS__*` settings)
for connection config — same env-var convention as `NatsSettings`.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Union

from mindtrace.core.messaging.nats.client import NatsClient


def _resolve_payload(args: argparse.Namespace) -> bytes:
    """Translate the `payload` / `--file` / `--json` args into the byte body sent on the wire.

    Precedence:
        --file PATH    → raw bytes from the file
        --json         → re-encode the positional payload as compact JSON
        <positional>   → utf-8 encoded
    """
    if getattr(args, "file", None):
        data = Path(args.file).read_bytes()
        return data
    payload = args.payload
    if getattr(args, "json", False):
        # Validate / round-trip the JSON so malformed input fails loudly here
        # rather than silently on the receiving end.
        parsed = json.loads(payload)
        return json.dumps(parsed, separators=(",", ":")).encode("utf-8")
    return payload.encode("utf-8") if isinstance(payload, str) else payload


def _format_body(data: Union[bytes, bytearray]) -> str:
    """Best-effort utf-8 print; fall back to `repr` for binary."""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return repr(bytes(data))


async def _cmd_publish(args: argparse.Namespace) -> int:
    body = _resolve_payload(args)
    async with NatsClient.connect() as nc:
        await nc.publish(args.subject, body)
        await nc.flush()
        print(f"published to {args.subject!r} ({len(body)} bytes)")
    return 0


async def _cmd_subscribe(args: argparse.Namespace) -> int:
    received = 0
    async with NatsClient.connect() as nc:
        async with nc.subscribe(args.subject) as sub:
            print(f"subscribed to {args.subject!r}; waiting for messages...")
            try:
                async for msg in sub:
                    received += 1
                    body = _format_body(msg.raw_data)
                    print(f"[{received}] subject={msg.subject!r} data={body!r}")
                    if args.count and received >= args.count:
                        return 0
            except asyncio.CancelledError:
                # Triggered by Ctrl-C through asyncio.run's signal handling.
                print(f"\nstopped after {received} messages.")
                return 0
    return 0


async def _cmd_request(args: argparse.Namespace) -> int:
    body = _resolve_payload(args)
    async with NatsClient.connect() as nc:
        reply = await nc.request(args.subject, body, timeout=args.timeout)
        print(_format_body(reply) if isinstance(reply, (bytes, bytearray)) else repr(reply))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m mindtrace.core.messaging.nats", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    pub = sub.add_parser("publish", help="publish a single message")
    pub.add_argument("subject")
    pub.add_argument("payload", nargs="?", default="", help="utf-8 payload (omit with --file)")
    pub.add_argument("--json", action="store_true", help="treat payload as JSON; re-encode compactly")
    pub.add_argument("--file", type=str, default=None, help="read raw payload bytes from PATH")

    sb = sub.add_parser("subscribe", help="subscribe to a subject and print messages")
    sb.add_argument("subject")
    sb.add_argument("--count", type=int, default=0, help="stop after N messages (0 = run forever)")

    rq = sub.add_parser("request", help="send a request and print the reply")
    rq.add_argument("subject")
    rq.add_argument("payload", nargs="?", default="", help="utf-8 payload (omit with --file)")
    rq.add_argument("--json", action="store_true", help="treat payload as JSON; re-encode compactly")
    rq.add_argument("--file", type=str, default=None, help="read raw payload bytes from PATH")
    rq.add_argument("--timeout", type=float, default=2.0)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    handler = {
        "publish": _cmd_publish,
        "subscribe": _cmd_subscribe,
        "request": _cmd_request,
    }.get(args.cmd)
    if handler is None:
        parser.print_help(sys.stderr)
        return 2
    try:
        return asyncio.run(handler(args))
    except KeyboardInterrupt:
        # Subscribe path handles this via CancelledError; this catch is for
        # the publish / request quick commands so Ctrl-C exits 130 cleanly.
        return 130


if __name__ == "__main__":
    sys.exit(main())

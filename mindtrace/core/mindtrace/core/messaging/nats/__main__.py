"""Minimal CLI for `NatsClient` — handy for ops smoke tests, not a load tester.

Usage:
    python -m mindtrace.core.messaging.nats publish <subject> <payload>
    python -m mindtrace.core.messaging.nats subscribe <subject> [--count N]
    python -m mindtrace.core.messaging.nats request <subject> <payload> [--timeout 2.0]

Reads `MINDTRACE_NATS__URLS` (and the other `MINDTRACE_NATS__*` settings)
for connection config — same env-var convention as `NatsSettings`.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from mindtrace.core.messaging.nats.client import NatsClient


async def _cmd_publish(args: argparse.Namespace) -> int:
    async with NatsClient.connect() as nc:
        await nc.publish(args.subject, args.payload.encode("utf-8") if isinstance(args.payload, str) else args.payload)
        await nc.flush()
        print(f"published to {args.subject!r} ({len(args.payload)} bytes)")
    return 0


async def _cmd_subscribe(args: argparse.Namespace) -> int:
    received = 0
    async with NatsClient.connect() as nc:
        async with nc.subscribe(args.subject) as sub:
            print(f"subscribed to {args.subject!r}; waiting for messages...")
            async for msg in sub:
                received += 1
                # Print as utf-8 if we can; otherwise the raw repr.
                try:
                    body = msg.raw_data.decode("utf-8")
                except UnicodeDecodeError:
                    body = repr(msg.raw_data)
                print(f"[{received}] subject={msg.subject!r} data={body!r}")
                if args.count and received >= args.count:
                    return 0
    return 0


async def _cmd_request(args: argparse.Namespace) -> int:
    async with NatsClient.connect() as nc:
        reply = await nc.request(args.subject, args.payload.encode("utf-8"), timeout=args.timeout)
        try:
            body = reply.decode("utf-8") if isinstance(reply, (bytes, bytearray)) else repr(reply)
        except UnicodeDecodeError:
            body = repr(reply)
        print(body)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m mindtrace.core.messaging.nats", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    pub = sub.add_parser("publish", help="publish a single message")
    pub.add_argument("subject")
    pub.add_argument("payload")

    sb = sub.add_parser("subscribe", help="subscribe to a subject and print messages")
    sb.add_argument("subject")
    sb.add_argument("--count", type=int, default=0, help="stop after N messages (0 = run forever)")

    rq = sub.add_parser("request", help="send a request and print the reply")
    rq.add_argument("subject")
    rq.add_argument("payload")
    rq.add_argument("--timeout", type=float, default=2.0)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.cmd == "publish":
        return asyncio.run(_cmd_publish(args))
    if args.cmd == "subscribe":
        return asyncio.run(_cmd_subscribe(args))
    if args.cmd == "request":
        return asyncio.run(_cmd_request(args))
    parser.print_help(sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())

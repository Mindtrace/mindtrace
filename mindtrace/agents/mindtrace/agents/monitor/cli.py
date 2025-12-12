import asyncio
import json
from pathlib import Path
from re import M
from datetime import datetime

import click
from rich.console import Console
from rich.syntax import Syntax

from mindtrace.agents.catalogue.agents import BaseAgentCLI
from mindtrace.agents.monitor.agent import MonitorAgent
from mindtrace.agents.monitor.config import MonitorAgentConfig

console = Console()


class MonitorAgentCLI(BaseAgentCLI):
    agent_class = MonitorAgent

    @classmethod
    def cli_group(cls) -> click.Group:
        @click.group()
        @click.pass_context
        def monitor(ctx):
            ctx.ensure_object(dict)

        @monitor.command("configure")
        @click.option("--config", "-c", "config_json", required=True)
        @click.pass_context
        def configure(ctx, config_json: str):
            config_json = json.loads(config_json)
            config = MonitorAgentConfig(extra_settings=[config_json])
            config.save_json(Path(config.MT_AGENT_PATHS.config_dir) / f"{MonitorAgent.agent_name}.json")
            ctx.obj["config"] = config
            click.secho("Saved:", fg="green")
            click.echo(json.dumps(config, indent=2))

        @monitor.command("query")
        @click.option("--query", "-q", "query", required=True)
        @click.option("--service", "-s", "service", required=True)
        @click.pass_context
        def query(ctx, query: str, service: str):
            config = MonitorAgentConfig()
            if Path(config.MT_AGENT_PATHS.config_dir).exists():
                config = config.load_json(Path(config.MT_AGENT_PATHS.config_dir) / f"{MonitorAgent.agent_name}.json")
            agent = cls.agent_class(config_override=config)
            result = asyncio.run(agent.query(query, service))
            
            # Pretty print JSON with syntax highlighting
            json_str = json.dumps(result, indent=2)
            json_syntax = Syntax(json_str, "json", theme="monokai", line_numbers=False, word_wrap=True)
            console.print(json_syntax)

        return monitor

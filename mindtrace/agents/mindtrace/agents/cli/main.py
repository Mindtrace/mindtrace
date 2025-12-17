import click

from mindtrace.agents.catalogue.agents import AgentRegistry
from mindtrace.agents.catalogue.cli_adapter import AgentCLIAdapter

AgentRegistry.register(
    name="monitor",
    description="AI-powered log monitoring and analysis agent",
    cli_module="mindtrace.agents.monitor.cli",
    cli_class="MonitorAgentCLI",
    version="1.0.0",
)


@click.group()
@click.version_option(version="0.6.0", prog_name="mindtrace")
def cli():
    pass


@cli.group(invoke_without_command=True)
@click.option("--list", "show_list", is_flag=True, help="List available agents")
@click.pass_context
def agents(ctx, show_list):
    if show_list:
        for name, info in AgentRegistry.all().items():
            click.echo(f"  - {name}: {info['description']}")
    elif ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


AgentCLIAdapter.register_all_commands(agents)


if __name__ == "__main__":
    cli()

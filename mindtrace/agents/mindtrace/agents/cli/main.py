"""Main CLI application for mindtrace tools."""

import typer

from mindtrace.agents.cli.tools import tools_app

app = typer.Typer(
    name="mindtrace",
    help="Mindtrace CLI - Tools and MCP Server Management",
    no_args_is_help=True,
)

# Add subcommands
app.add_typer(tools_app, name="tools", help="Manage and serve tools")


@app.command()
def version():
    """Show the version of mindtrace."""
    from mindtrace.agents import __version__
    typer.echo(f"mindtrace version {__version__}")


if __name__ == "__main__":
    app()


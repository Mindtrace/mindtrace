"""Main entry point for the Mindtrace Hardware CLI."""

import signal
import sys
from pathlib import Path

import typer
from typing_extensions import Annotated

from mindtrace.hardware.cli.commands.camera import app as camera_app
from mindtrace.hardware.cli.commands.plc import app as plc_app
from mindtrace.hardware.cli.commands.status import status_command
from mindtrace.hardware.cli.commands.stereo import app as stereo_app
from mindtrace.hardware.cli.core.logger import RichLogger, setup_logger
from mindtrace.hardware.cli.core.process_manager import ProcessManager
from mindtrace.hardware.cli.utils.display import show_banner

# Create main CLI app
app = typer.Typer(
    name="mindtrace-hw",
    help="Mindtrace Hardware CLI - Manage hardware services and devices.",
    no_args_is_help=False,
    rich_markup_mode="rich",
)

# Add subcommand apps
app.add_typer(camera_app, name="camera", help="Manage camera services")
app.add_typer(plc_app, name="plc", help="Manage PLC services")
app.add_typer(stereo_app, name="stereo", help="Manage stereo camera services")


@app.callback(invoke_without_command=True)
def main_callback(
    ctx: typer.Context,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Enable verbose output")] = False,
    version: Annotated[bool, typer.Option("--version", help="Show version")] = False,
):
    """Mindtrace Hardware CLI - Manage hardware services and devices."""
    # Handle version flag
    if version:
        from . import __version__

        typer.echo(f"mindtrace-hw version {__version__}")
        raise typer.Exit()

    # Show banner if no command specified
    if ctx.invoked_subcommand is None:
        show_banner()
        typer.echo("\nUse 'mindtrace-hw --help' for available commands")

    # Set up logging
    log_file = Path.home() / ".mindtrace" / "hw_cli.log"
    log_file.parent.mkdir(exist_ok=True)
    ctx.obj = setup_logger(verbose=verbose, log_file=log_file)


@app.command()
def status():
    """Show status of all hardware services."""
    status_command()


@app.command()
def stop():
    """Stop all hardware services."""
    logger = RichLogger()
    pm = ProcessManager()

    # Get all running services
    service_status = pm.get_status()
    running_services = [k for k, v in service_status.items() if v["running"]]

    if not running_services:
        logger.info("No services are running")
        return

    # Show what will be stopped
    camera_services = [s for s in running_services if "camera_api" in s or "configurator" in s]
    plc_services = [s for s in running_services if "plc" in s]
    stereo_services = [s for s in running_services if "stereo" in s]
    other_services = [
        s for s in running_services if s not in camera_services and s not in plc_services and s not in stereo_services
    ]

    if camera_services:
        logger.info(f"Stopping camera services: {', '.join(camera_services)}")
    if plc_services:
        logger.info(f"Stopping PLC services: {', '.join(plc_services)}")
    if stereo_services:
        logger.info(f"Stopping stereo camera services: {', '.join(stereo_services)}")
    if other_services:
        logger.info(f"Stopping other services: {', '.join(other_services)}")

    # Stop all services
    pm.stop_all()

    logger.success("All hardware services stopped")


@app.command()
def logs(
    service: Annotated[str, typer.Argument(help="Service name (camera, plc, stereo, all)")],
    follow: Annotated[bool, typer.Option("--follow", "-f", help="Follow log output")] = False,
):
    """View service logs."""
    logger = RichLogger()

    valid_services = ["camera", "plc", "stereo", "all"]
    if service not in valid_services:
        logger.error(f"Invalid service: {service}. Must be one of: {', '.join(valid_services)}")
        raise typer.Exit(1)

    if service == "camera":
        log_locations = [
            "API logs: Check console output where service was started",
            "App logs: mindtrace/hardware/apps/camera_configurator/app.log",
        ]
    elif service == "plc":
        log_locations = [
            "API logs: Check console output where service was started",
        ]
    elif service == "stereo":
        log_locations = [
            "API logs: Check console output where service was started",
        ]
    else:
        log_locations = [
            "CLI logs: ~/.mindtrace/hw_cli.log",
            "Service logs: Check console output where services were started",
        ]

    logger.info(f"Log locations for {service}:")
    for location in log_locations:
        typer.echo(f"  - {location}")

    if follow:
        logger.info("\nLog following not yet implemented")
        logger.info("Use 'tail -f <log_file>' to follow logs")


def handle_sigterm(signum, frame):
    """Handle SIGTERM signal for graceful shutdown."""
    logger = RichLogger()
    logger.info("\nReceived shutdown signal...")
    pm = ProcessManager()
    pm.stop_all()
    sys.exit(0)


def main():
    """Main entry point."""
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, handle_sigterm)
    signal.signal(signal.SIGINT, handle_sigterm)

    try:
        app()
    except Exception as e:
        logger = RichLogger()
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

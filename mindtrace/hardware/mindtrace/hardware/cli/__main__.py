"""Main entry point for the Mindtrace Hardware CLI."""

import sys
import signal
from pathlib import Path

import click

from .commands.camera import camera
from .commands.status import status_command
from .core.process_manager import ProcessManager
from .core.logger import ClickLogger, setup_logger
from .utils.display import show_banner


@click.group(invoke_without_command=True)
@click.option('-v', '--verbose', is_flag=True, help='Enable verbose output')
@click.option('--version', is_flag=True, help='Show version')
@click.pass_context
def cli(ctx, verbose: bool, version: bool):
    """Mindtrace Hardware CLI - Manage hardware services and devices."""
    # Handle version flag
    if version:
        from . import __version__
        click.echo(f"mindtrace-hw version {__version__}")
        ctx.exit()
    
    # Show banner if no command specified
    if ctx.invoked_subcommand is None:
        show_banner()
        click.echo("\nUse 'mindtrace-hw --help' for available commands")
    
    # Set up logging
    log_file = Path.home() / '.mindtrace' / 'hw_cli.log'
    log_file.parent.mkdir(exist_ok=True)
    ctx.obj = setup_logger(verbose=verbose, log_file=log_file)


# Add commands
cli.add_command(camera)
cli.add_command(status_command, name='status')


@cli.command()
def stop():
    """Stop all hardware services."""
    logger = ClickLogger()
    pm = ProcessManager()
    
    # Get all running services
    status = pm.get_status()
    running_services = [k for k, v in status.items() if v['running']]
    
    if not running_services:
        logger.info("No services are running")
        return
    
    # Show what will be stopped
    camera_services = [s for s in running_services if 'camera' in s or 'configurator' in s]
    other_services = [s for s in running_services if s not in camera_services]
    
    if camera_services:
        logger.info(f"Stopping camera services: {', '.join(camera_services)}")
    if other_services:
        logger.info(f"Stopping other services: {', '.join(other_services)}")
    
    # Stop all services
    pm.stop_all()
    
    logger.success("All hardware services stopped")


@cli.command()
@click.argument('service', type=click.Choice(['camera', 'all']))
@click.option('-f', '--follow', is_flag=True, help='Follow log output')
def logs(service: str, follow: bool):
    """View service logs.
    
    SERVICE: Service name (camera, all)
    """
    logger = ClickLogger()
    
    if service == 'camera':
        log_locations = [
            "API logs: Check console output where service was started",
            "App logs: mindtrace/hardware/apps/camera_configurator/app.log",
        ]
    else:
        log_locations = [
            "CLI logs: ~/.mindtrace/hw_cli.log",
            "Service logs: Check console output where services were started",
        ]
    
    logger.info(f"Log locations for {service}:")
    for location in log_locations:
        click.echo(f"  - {location}")
    
    if follow:
        # In a real implementation, we would tail the log files
        logger.info("\nLog following not yet implemented")
        logger.info("Use 'tail -f <log_file>' to follow logs")


def handle_sigterm(signum, frame):
    """Handle SIGTERM signal for graceful shutdown."""
    logger = ClickLogger()
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
        cli()
    except Exception as e:
        logger = ClickLogger()
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
"""Stereo camera service commands."""

import os
import time
import webbrowser

import click

from mindtrace.hardware.cli.core.logger import RichLogger
from mindtrace.hardware.cli.core.process_manager import ProcessManager
from mindtrace.hardware.cli.utils.display import console, format_status
from mindtrace.hardware.cli.utils.network import check_port_available, wait_for_service


@click.group()
def stereo():
    """Manage stereo camera services."""
    pass


@stereo.command()
@click.option(
    "--api-host",
    default=lambda: os.getenv("STEREO_CAMERA_API_HOST", "localhost"),
    help="Stereo Camera API service host",
)
@click.option(
    "--api-port",
    default=lambda: int(os.getenv("STEREO_CAMERA_API_PORT", "8004")),
    type=int,
    help="Stereo Camera API service port",
)
@click.option("--open-docs", is_flag=True, help="Open API documentation in browser")
def start(api_host: str, api_port: int, open_docs: bool):
    """Start stereo camera API service."""
    logger = RichLogger()
    pm = ProcessManager()

    # Check if service is already running
    if pm.is_service_running("stereo_camera_api"):
        logger.warning("Stereo Camera API is already running")
        if not click.confirm("Stop existing service and restart?"):
            return
        pm.stop_service("stereo_camera_api")
        time.sleep(1)

    # Check port availability
    if not check_port_available(api_host, api_port):
        logger.error(f"Port {api_port} is already in use on {api_host}")
        return

    try:
        # Start API service with spinner
        with console.status("[cyan]Starting Stereo Camera API...", spinner="dots") as status:
            pm.start_stereo_camera_api(api_host, api_port)

            # Wait for API to be ready
            if wait_for_service(api_host, api_port, timeout=10):
                status.update("[green]Stereo Camera API started")
            else:
                logger.error("Stereo Camera API failed to start (timeout)")
                pm.stop_service("stereo_camera_api")
                return

        logger.success(f"Stereo Camera API started → http://{api_host}:{api_port}")
        logger.info(f"  Swagger UI: http://{api_host}:{api_port}/docs")
        logger.info(f"  ReDoc: http://{api_host}:{api_port}/redoc")

        # Open browser if requested
        if open_docs:
            docs_url = f"http://{api_host}:{api_port}/docs"
            webbrowser.open(docs_url)
            logger.info(f"Opening browser: {docs_url}")

        logger.info("\nPress Ctrl+C to stop the service.")

        # Keep running until interrupted
        try:
            while True:
                # Check if process is still running
                if not pm.is_service_running("stereo_camera_api"):
                    logger.error("Stereo Camera API has stopped unexpectedly")
                    break

                time.sleep(1)

        except KeyboardInterrupt:
            logger.info("\n\nShutting down service...")

    except Exception as e:
        logger.error(f"Failed to start service: {e}")
        return

    finally:
        # Clean shutdown
        if pm.is_service_running("stereo_camera_api"):
            pm.stop_service("stereo_camera_api")
            logger.success("Stereo Camera API stopped")


@stereo.command()
def stop():
    """Stop stereo camera API service."""
    logger = RichLogger()
    pm = ProcessManager()

    logger.info("Stopping Stereo Camera API...")

    if pm.is_service_running("stereo_camera_api"):
        pm.stop_service("stereo_camera_api")
        logger.success("Stereo Camera API stopped")
    else:
        logger.info("Stereo Camera API was not running")


@stereo.command()
def status():
    """Show stereo camera service status."""
    pm = ProcessManager()

    # Get status for stereo camera service
    all_status = pm.get_status()
    stereo_status = {k: v for k, v in all_status.items() if k == "stereo_camera_api"}

    if not stereo_status:
        click.echo("Stereo Camera API is not configured.")
        click.echo("\nUse 'mindtrace-hw stereo start' to launch the service.")
        return

    click.echo("\nStereo Camera Service Status:")
    click.echo(format_status(stereo_status))

    # Show additional info if service is running
    if stereo_status.get("stereo_camera_api", {}).get("running"):
        info = stereo_status["stereo_camera_api"]
        url = f"http://{info['host']}:{info['port']}"
        click.echo("\nAccess URLs:")
        click.echo(f"  API: {url}")
        click.echo(f"  Swagger UI: {url}/docs")
        click.echo(f"  ReDoc: {url}/redoc")


@stereo.command()
def logs():
    """View stereo camera service logs."""
    logger = RichLogger()

    logger.info("Log viewing not yet implemented.")
    logger.info("Logs can be found in:")
    logger.info("  - API logs: Check console output where service was started")

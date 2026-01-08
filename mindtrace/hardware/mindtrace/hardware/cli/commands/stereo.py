"""Stereo camera service commands."""

import time
import webbrowser

import typer
from typing_extensions import Annotated

from mindtrace.hardware.cli.core.logger import RichLogger
from mindtrace.hardware.cli.core.process_manager import ProcessManager
from mindtrace.hardware.cli.utils.display import console, format_status
from mindtrace.hardware.cli.utils.network import check_port_available, wait_for_service

app = typer.Typer(help="Manage stereo camera services")


@app.command()
def start(
    api_host: Annotated[
        str, typer.Option("--api-host", help="Stereo Camera API service host", envvar="STEREO_CAMERA_API_HOST")
    ] = "localhost",
    api_port: Annotated[
        int, typer.Option("--api-port", help="Stereo Camera API service port", envvar="STEREO_CAMERA_API_PORT")
    ] = 8004,
    open_docs: Annotated[bool, typer.Option("--open-docs", help="Open API documentation in browser")] = False,
):
    """Start stereo camera API service."""
    logger = RichLogger()
    pm = ProcessManager()

    # Check if service is already running
    if pm.is_service_running("stereo_camera_api"):
        logger.warning("Stereo Camera API is already running")
        if not typer.confirm("Stop existing service and restart?"):
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

        logger.info("\nService running in background. Use 'mindtrace-hw stereo stop' to stop.")

    except Exception as e:
        logger.error(f"Failed to start service: {e}")


@app.command()
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


@app.command()
def status():
    """Show stereo camera service status."""
    pm = ProcessManager()

    # Get status for stereo camera service
    all_status = pm.get_status()
    stereo_status = {k: v for k, v in all_status.items() if k == "stereo_camera_api"}

    if not stereo_status:
        typer.echo("Stereo Camera API is not configured.")
        typer.echo("\nUse 'mindtrace-hw stereo start' to launch the service.")
        return

    typer.echo("\nStereo Camera Service Status:")
    format_status(stereo_status)

    # Show additional info if service is running
    if stereo_status.get("stereo_camera_api", {}).get("running"):
        info = stereo_status["stereo_camera_api"]
        url = f"http://{info['host']}:{info['port']}"
        typer.echo("\nAccess URLs:")
        typer.echo(f"  API: {url}")
        typer.echo(f"  Swagger UI: {url}/docs")
        typer.echo(f"  ReDoc: {url}/redoc")


@app.command()
def logs():
    """View stereo camera service logs."""
    logger = RichLogger()

    logger.info("Log viewing not yet implemented.")
    logger.info("Logs can be found in:")
    logger.info("  - API logs: Check console output where service was started")

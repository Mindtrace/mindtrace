"""3D Scanner service commands."""

import time
import webbrowser

import typer
from typing_extensions import Annotated

from mindtrace.hardware.cli.core.logger import RichLogger
from mindtrace.hardware.cli.core.process_manager import ProcessManager
from mindtrace.hardware.cli.utils.display import console, format_status
from mindtrace.hardware.cli.utils.network import ServiceTimeoutError, is_port_available, wait_for_service

app = typer.Typer(help="Manage 3D scanner services")


@app.command()
def start(
    api_host: Annotated[
        str, typer.Option("--api-host", help="3D Scanner API service host", envvar="SCANNER_3D_API_HOST")
    ] = "localhost",
    api_port: Annotated[
        int, typer.Option("--api-port", help="3D Scanner API service port", envvar="SCANNER_3D_API_PORT")
    ] = 8005,
    open_docs: Annotated[bool, typer.Option("--open-docs", help="Open API documentation in browser")] = False,
):
    """Start 3D scanner API service."""
    logger = RichLogger()
    pm = ProcessManager()

    # Check if service is already running
    if pm.is_service_running("scanner_3d_api"):
        logger.warning("3D Scanner API is already running")
        if not typer.confirm("Stop existing service and restart?"):
            return
        pm.stop_service("scanner_3d_api")
        time.sleep(1)

    # Check port availability
    if not is_port_available(api_host, api_port):
        logger.error(f"Port {api_port} is already in use on {api_host}")
        return

    try:
        # Start API service with spinner
        with console.status("[cyan]Starting 3D Scanner API...", spinner="dots") as status:
            pm.start_scanner_3d_api(api_host, api_port)

            # Wait for API to be ready
            try:
                wait_for_service(api_host, api_port, timeout=10)
                status.update("[green]3D Scanner API started")
            except ServiceTimeoutError:
                logger.error("3D Scanner API failed to start (timeout)")
                pm.stop_service("scanner_3d_api")
                return

        logger.success(f"3D Scanner API started → http://{api_host}:{api_port}")
        logger.info(f"  Swagger UI: http://{api_host}:{api_port}/docs")
        logger.info(f"  ReDoc: http://{api_host}:{api_port}/redoc")

        # Open browser if requested
        if open_docs:
            docs_url = f"http://{api_host}:{api_port}/docs"
            webbrowser.open(docs_url)
            logger.info(f"Opening browser: {docs_url}")

        logger.info("\nService running in background. Use 'mindtrace-hw scanner stop' to stop.")

    except Exception as e:
        logger.error(f"Failed to start service: {e}")


@app.command()
def stop():
    """Stop 3D scanner API service."""
    logger = RichLogger()
    pm = ProcessManager()

    logger.info("Stopping 3D Scanner API...")

    if pm.is_service_running("scanner_3d_api"):
        pm.stop_service("scanner_3d_api")
        logger.success("3D Scanner API stopped")
    else:
        logger.info("3D Scanner API was not running")


@app.command()
def status():
    """Show 3D scanner service status."""
    pm = ProcessManager()

    # Get status for 3D scanner service
    all_status = pm.get_status()
    scanner_status = {k: v for k, v in all_status.items() if k == "scanner_3d_api"}

    if not scanner_status:
        typer.echo("3D Scanner API is not configured.")
        typer.echo("\nUse 'mindtrace-hw scanner start' to launch the service.")
        return

    typer.echo("\n3D Scanner Service Status:")
    format_status(scanner_status)

    # Show additional info if service is running
    if scanner_status.get("scanner_3d_api", {}).get("running"):
        info = scanner_status["scanner_3d_api"]
        url = f"http://{info['host']}:{info['port']}"
        typer.echo("\nAccess URLs:")
        typer.echo(f"  API: {url}")
        typer.echo(f"  Swagger UI: {url}/docs")
        typer.echo(f"  ReDoc: {url}/redoc")


@app.command()
def logs():
    """View 3D scanner service logs."""
    logger = RichLogger()

    logger.info("Log viewing not yet implemented.")
    logger.info("Logs can be found in:")
    logger.info("  - API logs: Check console output where service was started")

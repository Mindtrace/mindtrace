"""Camera service commands."""

import time

import typer
from typing_extensions import Annotated

from mindtrace.hardware.cli.core.logger import RichLogger
from mindtrace.hardware.cli.core.process_manager import ProcessManager
from mindtrace.hardware.cli.utils.display import console, format_status
from mindtrace.hardware.cli.utils.network import check_port_available, wait_for_service

app = typer.Typer(help="Manage camera services")


@app.command()
def start(
    api_host: Annotated[
        str, typer.Option("--api-host", help="API service host", envvar="CAMERA_API_HOST")
    ] = "localhost",
    api_port: Annotated[int, typer.Option("--api-port", help="API service port", envvar="CAMERA_API_PORT")] = 8002,
    include_mocks: Annotated[bool, typer.Option("--include-mocks", help="Include mock cameras")] = False,
    open_docs: Annotated[bool, typer.Option("--open-docs", help="Open API documentation in browser")] = False,
):
    """Start camera API service (headless)."""
    logger = RichLogger()
    pm = ProcessManager()

    # Check if services are already running
    if pm.is_service_running("camera_api"):
        logger.warning("Camera API is already running")
        if not typer.confirm("Stop existing service and restart?"):
            return
        pm.stop_service("camera_api")
        time.sleep(1)

    # Check port availability
    if not check_port_available(api_host, api_port):
        logger.error(f"Port {api_port} is already in use on {api_host}")
        return

    try:
        # Start API service with spinner
        with console.status("[cyan]Starting Camera API...", spinner="dots") as status:
            pm.start_camera_api(api_host, api_port, include_mocks)

            # Wait for API to be ready
            if wait_for_service(api_host, api_port, timeout=10):
                status.update("[green]Camera API started")
            else:
                logger.error("Camera API failed to start (timeout)")
                pm.stop_service("camera_api")
                return

        logger.success(f"Camera API started → http://{api_host}:{api_port}")
        logger.info(f"  Swagger UI: http://{api_host}:{api_port}/docs")
        logger.info(f"  ReDoc: http://{api_host}:{api_port}/redoc")

        # Open browser to docs if requested
        if open_docs:
            import webbrowser

            docs_url = f"http://{api_host}:{api_port}/docs"
            webbrowser.open(docs_url)
            logger.info(f"Opening browser: {docs_url}")

        logger.info("\nService running in background. Use 'mindtrace-hw camera stop' to stop.")

    except Exception as e:
        logger.error(f"Failed to start service: {e}")


@app.command()
def stop():
    """Stop camera API service."""
    logger = RichLogger()
    pm = ProcessManager()

    logger.info("Stopping Camera API...")

    if pm.is_service_running("camera_api"):
        pm.stop_service("camera_api")
        logger.success("Camera API stopped")
    else:
        logger.info("Camera API was not running")


@app.command()
def status():
    """Show camera API service status."""
    pm = ProcessManager()

    # Get status for camera API
    all_status = pm.get_status()
    camera_status = {k: v for k, v in all_status.items() if k == "camera_api"}

    if not camera_status:
        typer.echo("Camera API is not running.")
        typer.echo("\nUse 'mindtrace-hw camera start' to launch the service.")
        return

    typer.echo("\nCamera API Status:")
    format_status(camera_status)

    # Show access URLs if running
    if camera_status.get("camera_api", {}).get("running"):
        info = camera_status["camera_api"]
        host = info["host"]
        port = info["port"]
        typer.echo("\nAccess URLs:")
        typer.echo(f"  API: http://{host}:{port}")
        typer.echo(f"  Swagger UI: http://{host}:{port}/docs")
        typer.echo(f"  ReDoc: http://{host}:{port}/redoc")


@app.command()
def logs():
    """View camera API service logs."""
    logger = RichLogger()

    # Provide guidance on log locations
    logger.info("Log viewing not yet implemented.")
    logger.info("Logs can be found in:")
    logger.info("  - API logs: Check console output")

"""PLC service commands."""

import os
import time

import click

from mindtrace.hardware.cli.core.logger import RichLogger
from mindtrace.hardware.cli.core.process_manager import ProcessManager
from mindtrace.hardware.cli.utils.display import console, format_status
from mindtrace.hardware.cli.utils.network import check_port_available, wait_for_service


@click.group()
def plc():
    """Manage PLC services."""
    pass


@plc.command()
@click.option("--api-host", default=lambda: os.getenv("PLC_API_HOST", "localhost"), help="API service host")
@click.option("--api-port", default=lambda: int(os.getenv("PLC_API_PORT", "8003")), type=int, help="API service port")
def start(api_host: str, api_port: int):
    """Start PLC API service."""
    logger = RichLogger()
    pm = ProcessManager()

    # Check if service is already running
    if pm.is_service_running("plc_api"):
        logger.warning("PLC API is already running")
        if not click.confirm("Stop existing service and restart?"):
            return
        pm.stop_service("plc_api")
        time.sleep(1)

    # Check port availability
    if not check_port_available(api_host, api_port):
        logger.error(f"Port {api_port} is already in use on {api_host}")
        return

    try:
        # Start API service with spinner
        with console.status("[cyan]Starting PLC API...", spinner="dots") as status:
            pm.start_plc_api(api_host, api_port)

            # Wait for API to be ready
            if wait_for_service(api_host, api_port, timeout=10):
                status.update("[green]PLC API started")
            else:
                logger.error("PLC API failed to start (timeout)")
                pm.stop_service("plc_api")
                return

        logger.success(f"PLC API started → http://{api_host}:{api_port}")
        logger.info("\nPress Ctrl+C to stop the service.")

        # Keep running until interrupted
        try:
            while True:
                # Check if process is still running
                if not pm.is_service_running("plc_api"):
                    logger.error("PLC API has stopped unexpectedly")
                    break

                time.sleep(1)

        except KeyboardInterrupt:
            logger.info("\n\nShutting down service...")

    except Exception as e:
        logger.error(f"Failed to start service: {e}")
        return

    finally:
        # Clean shutdown
        if pm.is_service_running("plc_api"):
            pm.stop_service("plc_api")
            logger.success("PLC API stopped")


@plc.command()
def stop():
    """Stop PLC API service."""
    logger = RichLogger()
    pm = ProcessManager()

    logger.info("Stopping PLC Service...")

    # Stop API
    if pm.is_service_running("plc_api"):
        pm.stop_service("plc_api")
        logger.success("PLC API stopped")
    else:
        logger.info("PLC API was not running")


@plc.command()
def status():
    """Show PLC service status."""
    pm = ProcessManager()

    # Get status for PLC services
    all_status = pm.get_status()
    plc_status = {k: v for k, v in all_status.items() if k in ["plc_api"]}

    if not plc_status:
        click.echo("No PLC services configured.")
        click.echo("\nUse 'mindtrace-hw plc start' to launch the service.")
        return

    click.echo("\nPLC Service Status:")
    click.echo(format_status(plc_status))

    # Show additional info if service is running
    if plc_status.get("plc_api", {}).get("running"):
        info = plc_status["plc_api"]
        url = f"http://{info['host']}:{info['port']}"
        click.echo("\nAccess URL:")
        click.echo(f"  PLC API: {url}")
        click.echo(f"  API Docs: {url}/docs")


@plc.command()
def logs():
    """View PLC service logs."""
    logger = RichLogger()

    # This would need to be implemented to capture and display logs
    # For now, provide guidance
    logger.info("Log viewing not yet implemented.")
    logger.info("Logs can be found in:")
    logger.info("  - API logs: Check console output or service logs")

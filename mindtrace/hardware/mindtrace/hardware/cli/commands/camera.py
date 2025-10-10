"""Camera service commands."""

import os
import time
import webbrowser

import click

from ..core.logger import ClickLogger
from ..core.process_manager import ProcessManager
from ..utils.display import format_status
from ..utils.network import check_port_available, wait_for_service


@click.group()
def camera():
    """Manage camera services."""
    pass


@camera.command()
@click.option("--api-host", default=lambda: os.getenv("CAMERA_API_HOST", "localhost"), help="API service host")
@click.option(
    "--api-port", default=lambda: int(os.getenv("CAMERA_API_PORT", "8002")), type=int, help="API service port"
)
@click.option("--app-host", default=lambda: os.getenv("CAMERA_UI_HOST", "localhost"), help="Configurator app host")
@click.option(
    "--app-port",
    default=lambda: int(os.getenv("CAMERA_UI_FRONTEND_PORT", "3000")),
    type=int,
    help="Configurator app port",
)
@click.option(
    "--backend-port",
    default=lambda: int(os.getenv("CAMERA_UI_BACKEND_PORT", "8000")),
    type=int,
    help="Reflex backend port",
)
@click.option("--api-only", is_flag=True, help="Start only API service")
@click.option("--include-mocks", is_flag=True, help="Include mock cameras")
def start(
    api_host: str, api_port: int, app_host: str, app_port: int, backend_port: int, api_only: bool, include_mocks: bool
):
    """Start camera services."""
    logger = ClickLogger()
    pm = ProcessManager()

    # Check if services are already running
    if pm.is_service_running("camera_api"):
        logger.warning("Camera API is already running")
        if not click.confirm("Stop existing service and restart?"):
            return
        pm.stop_service("camera_api")
        time.sleep(1)

    if not api_only and pm.is_service_running("configurator"):
        logger.warning("Camera Configurator is already running")
        if not click.confirm("Stop existing service and restart?"):
            return
        pm.stop_service("configurator")
        time.sleep(1)

    # Check port availability
    if not check_port_available(api_host, api_port):
        logger.error(f"Port {api_port} is already in use on {api_host}")
        return

    if not api_only and not check_port_available(app_host, app_port):
        logger.error(f"Port {app_port} is already in use on {app_host}")
        return

    logger.progress("Starting Camera Services...")

    try:
        # Start API service
        pm.start_camera_api(api_host, api_port, include_mocks)

        # Wait for API to be ready
        if wait_for_service(api_host, api_port, timeout=10):
            logger.success(f"Camera API started → http://{api_host}:{api_port}")
        else:
            logger.error("Camera API failed to start (timeout)")
            pm.stop_service("camera_api")
            return

        if not api_only:
            # Start configurator app
            time.sleep(1)  # Give API a moment to fully initialize
            pm.start_configurator(app_host, app_port, backend_port)

            # Wait for app to be ready
            if wait_for_service(app_host, app_port, timeout=15):
                logger.success(f"Camera Configurator started → http://{app_host}:{app_port}")

                # Open browser
                app_url = f"http://{app_host}:{app_port}"
                webbrowser.open(app_url)
                logger.info(f"🌐 Opening browser → {app_url}")
            else:
                logger.error("Camera Configurator failed to start (timeout)")
                pm.stop_service("configurator")
                pm.stop_service("camera_api")
                return

        logger.info("\nPress Ctrl+C to stop all services.")

        # Keep running until interrupted
        try:
            while True:
                # Check if processes are still running
                if not pm.is_service_running("camera_api"):
                    logger.error("Camera API has stopped unexpectedly")
                    break

                if not api_only and not pm.is_service_running("configurator"):
                    logger.error("Camera Configurator has stopped unexpectedly")
                    break

                time.sleep(1)

        except KeyboardInterrupt:
            logger.info("\n\nShutting down services...")

    except Exception as e:
        logger.error(f"Failed to start services: {e}")
        return

    finally:
        # Clean shutdown
        if not api_only and pm.is_service_running("configurator"):
            pm.stop_service("configurator")
            logger.success("Camera Configurator stopped")

        if pm.is_service_running("camera_api"):
            pm.stop_service("camera_api")
            logger.success("Camera API stopped")


@camera.command()
def stop():
    """Stop camera services."""
    logger = ClickLogger()
    pm = ProcessManager()

    logger.info("Stopping Camera Services...")

    stopped_any = False

    # Stop configurator first (depends on API)
    if pm.is_service_running("configurator"):
        pm.stop_service("configurator")
        logger.success("Camera Configurator stopped")
        stopped_any = True

    # Stop API
    if pm.is_service_running("camera_api"):
        pm.stop_service("camera_api")
        logger.success("Camera API stopped")
        stopped_any = True

    if not stopped_any:
        logger.info("No camera services were running")
    else:
        logger.success("All camera services stopped")


@camera.command()
def status():
    """Show camera service status."""
    pm = ProcessManager()

    # Get status for camera services
    all_status = pm.get_status()
    camera_status = {k: v for k, v in all_status.items() if k in ["camera_api", "configurator"]}

    if not camera_status:
        click.echo("No camera services configured.")
        click.echo("\nUse 'mindtrace-hw camera start' to launch services.")
        return

    click.echo("\nCamera Services Status:")
    click.echo(format_status(camera_status))

    # Show additional info if services are running
    running_services = [k for k, v in camera_status.items() if v["running"]]
    if running_services:
        click.echo("\nAccess URLs:")
        for service in running_services:
            info = camera_status[service]
            url = f"http://{info['host']}:{info['port']}"
            display_name = service.replace("_", " ").title()
            click.echo(f"  {display_name}: {url}")


@camera.command()
def logs():
    """View camera service logs."""
    logger = ClickLogger()

    # This would need to be implemented to capture and display logs
    # For now, provide guidance
    logger.info("Log viewing not yet implemented.")
    logger.info("Logs can be found in:")
    logger.info("  - API logs: Check console output")
    logger.info("  - App logs: mindtrace/hardware/apps/camera_configurator/app.log")

"""Camera service commands."""

import asyncio
import os
import sys
import time
import webbrowser
from pathlib import Path
from typing import Optional

import click
from rich import box
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn
from rich.table import Table

from ..core.process_manager import ProcessManager
from ..core.logger import RichLogger
from ..utils.display import format_status, show_banner, console, print_test_summary
from ..utils.network import check_port_available, wait_for_service


@click.group()
def camera():
    """Manage camera services."""
    pass


@camera.command()
@click.option('--api-host', default=lambda: os.getenv('CAMERA_API_HOST', 'localhost'), help='API service host')
@click.option('--api-port', default=lambda: int(os.getenv('CAMERA_API_PORT', '8002')), type=int, help='API service port')
@click.option('--app-host', default=lambda: os.getenv('CAMERA_UI_HOST', 'localhost'), help='Configurator app host')
@click.option('--app-port', default=lambda: int(os.getenv('CAMERA_UI_FRONTEND_PORT', '3000')), type=int, help='Configurator app port')
@click.option('--backend-port', default=lambda: int(os.getenv('CAMERA_UI_BACKEND_PORT', '8000')), type=int, help='Reflex backend port')
@click.option('--api-only', is_flag=True, help='Start only API service')
@click.option('--include-mocks', is_flag=True, help='Include mock cameras')
def start(api_host: str, api_port: int, app_host: str, app_port: int, backend_port: int,
         api_only: bool, include_mocks: bool):
    """Start camera services."""
    logger = RichLogger()
    pm = ProcessManager()
    
    # Check if services are already running
    if pm.is_service_running('camera_api'):
        logger.warning("Camera API is already running")
        if not click.confirm("Stop existing service and restart?"):
            return
        pm.stop_service('camera_api')
        time.sleep(1)
    
    if not api_only and pm.is_service_running('configurator'):
        logger.warning("Camera Configurator is already running")
        if not click.confirm("Stop existing service and restart?"):
            return
        pm.stop_service('configurator')
        time.sleep(1)
    
    # Check port availability
    if not check_port_available(api_host, api_port):
        logger.error(f"Port {api_port} is already in use on {api_host}")
        return
    
    if not api_only and not check_port_available(app_host, app_port):
        logger.error(f"Port {app_port} is already in use on {app_host}")
        return

    try:
        # Start API service with spinner
        with console.status("[cyan]Starting Camera API...", spinner="dots") as status:
            api_process = pm.start_camera_api(api_host, api_port, include_mocks)

            # Wait for API to be ready
            if wait_for_service(api_host, api_port, timeout=10):
                status.update("[green]Camera API started")
            else:
                logger.error("Camera API failed to start (timeout)")
                pm.stop_service('camera_api')
                return

        logger.success(f"Camera API started → http://{api_host}:{api_port}")

        if not api_only:
            # Start configurator app with spinner
            time.sleep(1)  # Give API a moment to fully initialize

            with console.status("[cyan]Starting Camera Configurator...", spinner="dots") as status:
                app_process = pm.start_configurator(app_host, app_port, backend_port)

                # Wait for app to be ready
                if wait_for_service(app_host, app_port, timeout=15):
                    status.update("[green]Camera Configurator started")
                else:
                    logger.error("Camera Configurator failed to start (timeout)")
                    pm.stop_service('configurator')
                    pm.stop_service('camera_api')
                    return

            logger.success(f"Camera Configurator started → http://{app_host}:{app_port}")

            # Open browser
            app_url = f"http://{app_host}:{app_port}"
            webbrowser.open(app_url)
            logger.info(f"Opening browser: {app_url}")
        
        logger.info("\nPress Ctrl+C to stop all services.")
        
        # Keep running until interrupted
        try:
            while True:
                # Check if processes are still running
                if not pm.is_service_running('camera_api'):
                    logger.error("Camera API has stopped unexpectedly")
                    break
                
                if not api_only and not pm.is_service_running('configurator'):
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
        if not api_only and pm.is_service_running('configurator'):
            pm.stop_service('configurator')
            logger.success("Camera Configurator stopped")
        
        if pm.is_service_running('camera_api'):
            pm.stop_service('camera_api')
            logger.success("Camera API stopped")


@camera.command()
def stop():
    """Stop camera services."""
    logger = RichLogger()
    pm = ProcessManager()
    
    logger.info("Stopping Camera Services...")
    
    stopped_any = False
    
    # Stop configurator first (depends on API)
    if pm.is_service_running('configurator'):
        pm.stop_service('configurator')
        logger.success("Camera Configurator stopped")
        stopped_any = True
    
    # Stop API
    if pm.is_service_running('camera_api'):
        pm.stop_service('camera_api')
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
    camera_status = {
        k: v for k, v in all_status.items() 
        if k in ['camera_api', 'configurator']
    }
    
    if not camera_status:
        click.echo("No camera services configured.")
        click.echo("\nUse 'mindtrace-hw camera start' to launch services.")
        return
    
    click.echo("\nCamera Services Status:")
    click.echo(format_status(camera_status))
    
    # Show additional info if services are running
    running_services = [k for k, v in camera_status.items() if v['running']]
    if running_services:
        click.echo("\nAccess URLs:")
        for service in running_services:
            info = camera_status[service]
            url = f"http://{info['host']}:{info['port']}"
            display_name = service.replace('_', ' ').title()
            click.echo(f"  {display_name}: {url}")


@camera.command()
def logs():
    """View camera service logs."""
    logger = RichLogger()

    # This would need to be implemented to capture and display logs
    # For now, provide guidance
    logger.info("Log viewing not yet implemented.")
    logger.info("Logs can be found in:")
    logger.info("  - API logs: Check console output")
    logger.info("  - App logs: mindtrace/hardware/apps/camera_configurator/app.log")


@camera.command()
@click.option('--config', '-c', help='Test configuration to run (e.g., smoke_test)')
@click.option('--list', 'list_configs', is_flag=True, help='List available test configurations')
@click.option('--api-host', default='localhost', help='Camera API host')
@click.option('--api-port', default=8002, type=int, help='Camera API port')
@click.option('-v', '--verbose', is_flag=True, help='Enable verbose output')
def test(config: Optional[str], list_configs: bool, api_host: str, api_port: int, verbose: bool):
    """Run camera test scenarios."""
    logger = RichLogger()

    # Get test suite path
    test_suite_path = Path(__file__).parent.parent.parent.parent / "test_suite"
    sys.path.insert(0, str(test_suite_path.parent))

    try:
        from mindtrace.hardware.test_suite.cameras.config_loader import list_available_configs
        from mindtrace.hardware.test_suite.cameras.scenario_factory import create_scenario_from_config
        from mindtrace.hardware.test_suite.cameras.runner import CameraTestRunner
        from mindtrace.hardware.test_suite.core.monitor import HardwareMonitor
    except ImportError as e:
        logger.error(f"Failed to import test suite: {e}")
        logger.info("Make sure the test suite is properly installed")
        return

    # List available configs
    if list_configs:
        try:
            configs = list_available_configs()

            table = Table(title="Available Test Configurations", box=box.ROUNDED, show_header=False)
            table.add_column("Configuration", style="cyan", no_wrap=True)

            for config_name in configs:
                table.add_row(config_name)

            console.print(table)
            console.print(f"\n[dim]Total: {len(configs)} configurations[/]")
            console.print("[cyan]Run a test: camera test --config <name>[/]")
            return
        except Exception as e:
            logger.error(f"Failed to list configs: {e}")
            return

    # Validate config argument
    if not config:
        logger.error("No test configuration specified")
        click.echo("Use --list to see available configurations")
        click.echo("Example: camera test --config smoke_test")
        return

    # Check if API is running
    pm = ProcessManager()
    if not pm.is_service_running('camera_api'):
        logger.warning("Camera API is not running")
        if not click.confirm("Start Camera API now?"):
            logger.info("Camera API must be running to execute tests")
            return

        # Start API with spinner
        try:
            with console.status("[cyan]Starting Camera API...", spinner="dots") as status:
                pm.start_camera_api(api_host, api_port, include_mocks=False)
                if wait_for_service(api_host, api_port, timeout=10):
                    status.update("[green]Camera API started")
                    logger.success(f"Camera API started → http://{api_host}:{api_port}")
                else:
                    logger.error("Camera API failed to start")
                    return
        except Exception as e:
            logger.error(f"Failed to start Camera API: {e}")
            return

    # Run test
    logger.progress(f"Loading test configuration: {config}")

    try:
        scenario = create_scenario_from_config(config)
        logger.info(f"Test: {scenario.name}")
        logger.info(f"Description: {scenario.description}")
        click.echo("")

        # Run the test scenario with progress display
        async def run_test():
            async with CameraTestRunner(scenario.api_base_url) as runner:
                monitor = HardwareMonitor(scenario.name)

                # Create progress display
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    TaskProgressColumn(),
                    TimeElapsedColumn(),
                    console=console,
                ) as progress:
                    # Add progress task
                    task_id = progress.add_task(
                        f"[cyan]Executing {scenario.name}...",
                        total=len(scenario.operations)
                    )

                    # Progress callback
                    def on_progress(op_index: int, op_total: int, op_name: str, success: bool):
                        progress.update(
                            task_id,
                            completed=op_index + 1,
                            description=f"[cyan]Operation {op_index + 1}/{op_total}: [{'green' if success else 'red'}]{op_name}"
                        )

                    # Execute with progress callback
                    result = await runner.execute_scenario(scenario, monitor, progress_callback=on_progress)

                return monitor, result

        # Execute test
        monitor, result = asyncio.run(run_test())

        # Print summary using Rich formatting (CLI layer)
        click.echo("")
        summary = monitor.get_summary()
        print_test_summary(summary, monitor.devices_hung)

        # Determine exit based on success rate
        if result.success_rate >= scenario.expected_success_rate:
            logger.success(f"TEST PASSED (Success rate: {result.success_rate:.1%})")
            sys.exit(0)
        else:
            logger.error(f"TEST FAILED (Success rate: {result.success_rate:.1%}, Expected: {scenario.expected_success_rate:.1%})")
            sys.exit(2)

    except FileNotFoundError as e:
        logger.error(f"Test configuration not found: {config}")
        click.echo("Use --list to see available configurations")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Test execution failed: {e}")
        if verbose:
            import traceback
            click.echo(traceback.format_exc())
        sys.exit(1)
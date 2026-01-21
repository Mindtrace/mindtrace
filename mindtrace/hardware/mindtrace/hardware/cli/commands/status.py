"""Status command for all hardware services."""

import typer

from mindtrace.hardware.cli.core.process_manager import ProcessManager
from mindtrace.hardware.cli.utils.display import print_service_box


def status_command():
    """Show status of all hardware services."""
    pm = ProcessManager()

    # Get status of all services
    all_status = pm.get_status()

    # Categorize services
    camera_services = {}
    plc_services = {}
    sensor_services = {}
    other_services = {}

    for service_name, info in all_status.items():
        if "camera" in service_name or "configurator" in service_name:
            camera_services[service_name] = info
        elif "plc" in service_name:
            plc_services[service_name] = info
        elif "sensor" in service_name:
            sensor_services[service_name] = info
        else:
            other_services[service_name] = info

    # Display header
    typer.echo("\n" + "=" * 50)
    typer.echo("     Mindtrace Hardware Services Status")
    typer.echo("=" * 50 + "\n")

    # Display each category
    if camera_services:
        print_service_box("Camera Services", camera_services)
        typer.echo()

    if plc_services:
        print_service_box("PLC Services", plc_services)
        typer.echo()

    if sensor_services:
        print_service_box("Sensor Services", sensor_services)
        typer.echo()

    if other_services:
        print_service_box("Other Services", other_services)
        typer.echo()

    if not all_status:
        typer.echo("No services are currently running.\n")
        typer.echo("Available commands:")
        typer.echo("  mindtrace-hw camera start    - Start camera services")
        typer.echo("  mindtrace-hw --help          - Show all available commands")
    else:
        # Show summary
        running_count = sum(1 for s in all_status.values() if s["running"])
        total_count = len(all_status)

        typer.echo(f"Summary: {running_count}/{total_count} services running")

        if running_count > 0:
            typer.echo("\nUse 'mindtrace-hw stop' to stop all services")
            typer.echo("Use 'mindtrace-hw [service] stop' to stop specific service")

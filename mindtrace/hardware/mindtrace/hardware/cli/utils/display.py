"""Display utilities for CLI output using Rich."""

from typing import Any, Dict, List, Optional

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


def format_status(status: Dict[str, Any]) -> None:
    """Format and display service status.

    Args:
        status: Status dictionary from ProcessManager
    """
    if not status:
        console.print("No services running.", style="yellow")
        return

    # Create table
    table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan")
    table.add_column("Service", style="cyan", no_wrap=True)
    table.add_column("Status", justify="center")
    table.add_column("URL", style="blue")
    table.add_column("PID", justify="right", style="dim")
    table.add_column("Uptime", justify="right", style="dim")
    table.add_column("Memory", justify="right", style="dim")

    for service_name, info in status.items():
        # Format service name
        display_name = service_name.replace("_", " ").title()

        # Status with indicator
        if info["running"]:
            status_text = "[✓] Running"
            status_style = "green"
        else:
            status_text = "[✗] Stopped"
            status_style = "red"

        # URL or empty
        url = f"http://{info['host']}:{info['port']}" if info["running"] else ""

        # PID or empty
        pid = str(info["pid"]) if info["running"] else ""

        # Uptime or empty
        uptime = info.get("uptime", "") if info["running"] else ""

        # Memory or empty
        memory = f"{info.get('memory_mb', 0)} MB" if info["running"] and "memory_mb" in info else ""

        table.add_row(display_name, f"[{status_style}]{status_text}[/]", url, pid, uptime, memory)

    console.print(table)


def print_table(data: List[Dict[str, Any]], headers: Optional[List[str]] = None):
    """Print data as a formatted table.

    Args:
        data: List of dictionaries to display
        headers: Optional header names
    """
    if not data:
        console.print("No data to display.", style="yellow")
        return

    if headers is None and data:
        headers = list(data[0].keys())

    # Create table
    table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan")

    for header in headers:
        table.add_column(header, style="white")

    for row in data:
        table.add_row(*[str(row.get(h, "")) for h in headers])

    console.print(table)


def print_service_box(title: str, services: Dict[str, Dict[str, Any]]):
    """Print services in a nice panel format.

    Args:
        title: Panel title
        services: Service information dictionary
    """
    if not services:
        content = "[yellow]No services configured[/yellow]"
    else:
        lines = []
        for service_name, info in services.items():
            display_name = service_name.replace("_", " ").title()

            if info.get("running"):
                status = f"[green][✓] Running[/green] (port {info.get('port', '?')})"
            else:
                status = "[red][✗] Stopped[/red]"

            lines.append(f"{display_name:<20} {status}")

        content = "\n".join(lines)

    panel = Panel(content, title=f"[bold cyan]{title}[/]", box=box.ROUNDED, border_style="cyan")

    console.print(panel)


def show_banner():
    """Display the CLI banner."""
    banner_text = """
[bold cyan]Mindtrace Hardware CLI[/]
Manage hardware services & devices
    """
    panel = Panel(banner_text.strip(), box=box.DOUBLE, border_style="cyan", padding=(1, 2))
    console.print(panel)


def print_list(items: List[str], title: Optional[str] = None, style: str = "white"):
    """Print a list of items.

    Args:
        items: List of strings to display
        title: Optional title for the list
        style: Rich style for items
    """
    if title:
        console.print(f"\n[bold cyan]{title}[/]")

    for item in items:
        console.print(f"  • {item}", style=style)


def print_test_summary(summary: Any, devices_hung: set = None):
    """Print Rich-formatted test summary.

    Args:
        summary: MetricsSummary object from test monitor
        devices_hung: Optional set of hung device names
    """
    # Create main results table
    results_table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan")
    results_table.add_column("Metric", style="cyan", no_wrap=True)
    results_table.add_column("Value", justify="right")

    # Add results
    results_table.add_row("Duration", f"{summary.duration:.2f}s")
    results_table.add_row("Total Operations", str(summary.total_operations))
    results_table.add_row(
        "[green]Success[/green]", f"[green]{summary.successful_operations} ({summary.success_rate:.1%})[/green]"
    )
    if summary.failed_operations > 0:
        results_table.add_row("[red]Failed[/red]", f"[red]{summary.failed_operations}[/red]")
    if summary.timeout_operations > 0:
        results_table.add_row("[yellow]Timeout[/yellow]", f"[yellow]{summary.timeout_operations}[/yellow]")

    # Create performance table
    perf_table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan")
    perf_table.add_column("Performance Metric", style="cyan")
    perf_table.add_column("Value", justify="right")

    perf_table.add_row("Average Time", f"{summary.average_operation_time:.3f}s")
    perf_table.add_row("Min Time", f"{summary.min_operation_time:.3f}s")
    perf_table.add_row("Max Time", f"{summary.max_operation_time:.3f}s")
    perf_table.add_row("Operations/sec", f"{summary.operations_per_second:.2f}")

    # Print title panel
    console.print()
    console.print(
        Panel(f"[bold cyan]Test Results: {summary.scenario_name}[/bold cyan]", box=box.DOUBLE, border_style="cyan")
    )

    # Print tables
    console.print(results_table)
    console.print()
    console.print(perf_table)

    # Print errors table if any
    if summary.top_errors:
        console.print()
        error_table = Table(box=box.ROUNDED, show_header=True, header_style="bold red")
        error_table.add_column("Error Type", style="red")
        error_table.add_column("Count", justify="right", style="red")

        for error_type, count in summary.top_errors:
            error_table.add_row(error_type, str(count))

        console.print(error_table)

    # Print hung devices if any
    if devices_hung:
        console.print()
        console.print(
            Panel(
                f"[yellow]Hung Devices: {', '.join(sorted(devices_hung))}[/yellow]",
                box=box.ROUNDED,
                border_style="yellow",
                title="[bold yellow]Warning[/bold yellow]",
            )
        )

    console.print()

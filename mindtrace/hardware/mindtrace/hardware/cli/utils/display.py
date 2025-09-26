"""Display utilities for CLI output."""

from typing import List, Dict, Any, Optional
import click
from tabulate import tabulate


def format_status(status: Dict[str, Any]) -> str:
    """Format service status for display.
    
    Args:
        status: Status dictionary from ProcessManager
        
    Returns:
        Formatted status string
    """
    if not status:
        return "No services running."
    
    lines = []
    lines.append("━" * 50)
    
    for service_name, info in status.items():
        # Service name with status icon
        if info['running']:
            status_icon = "✅"
            status_text = "Running"
        else:
            status_icon = "❌"
            status_text = "Stopped"
        
        # Format service name
        display_name = service_name.replace('_', ' ').title()
        lines.append(f"{display_name:20} {status_icon} {status_text}")
        
        # Add details if running
        if info['running']:
            url = f"http://{info['host']}:{info['port']}"
            lines.append(f"{'':20} → {url}")
            lines.append(f"{'':20} PID: {info['pid']}")
            
            if 'uptime' in info:
                lines.append(f"{'':20} Uptime: {info['uptime']}")
            
            if 'memory_mb' in info:
                lines.append(f"{'':20} Memory: {info['memory_mb']} MB")
        
        lines.append("")
    
    lines.append("━" * 50)
    return '\n'.join(lines)


def print_table(data: List[Dict[str, Any]], headers: Optional[List[str]] = None):
    """Print data as a formatted table.
    
    Args:
        data: List of dictionaries to display
        headers: Optional header names
    """
    if not data:
        click.echo("No data to display.")
        return
    
    if headers is None and data:
        headers = list(data[0].keys())
    
    table_data = []
    for row in data:
        table_data.append([row.get(h, '') for h in headers])
    
    click.echo(tabulate(table_data, headers=headers, tablefmt='grid'))


def print_service_box(title: str, services: Dict[str, Dict[str, Any]]):
    """Print services in a nice box format.
    
    Args:
        title: Box title
        services: Service information dictionary
    """
    width = 50
    
    # Top border
    click.echo("┌" + "─" * (width - 2) + "┐")
    
    # Title
    title_padded = f" {title} ".center(width - 2)
    click.echo("│" + title_padded + "│")
    
    # Separator
    click.echo("├" + "─" * (width - 2) + "┤")
    
    # Services
    if not services:
        no_services = "No services configured".center(width - 2)
        click.echo("│" + no_services + "│")
    else:
        for service_name, info in services.items():
            # Format service line
            display_name = service_name.replace('_', ' ').title()
            if info.get('running'):
                status = click.style("✅ Running", fg='green')
                url = f"(port {info.get('port', '?')})"
            else:
                status = click.style("⭕ Stopped", fg='yellow')
                url = ""
            
            # Calculate padding for alignment
            name_part = f"{display_name}:"
            status_part = f"{status} {url}"
            
            # Create the line with proper spacing
            line = f" {name_part:<20} {status_part}"
            
            # Ensure line fits in box
            if len(click.unstyle(line)) > width - 2:
                line = line[:width-5] + "..."
            else:
                line = line.ljust(width - 2)
            
            click.echo("│" + line + "│")
    
    # Bottom border
    click.echo("└" + "─" * (width - 2) + "┘")


def show_banner():
    """Display the CLI banner."""
    banner = """
╔══════════════════════════════════════════════╗
║     Mindtrace Hardware CLI                   ║
║     Manage hardware services & devices       ║
╚══════════════════════════════════════════════╝
    """
    click.echo(click.style(banner, fg='cyan'))


def progress_spinner(message: str):
    """Show a progress spinner.
    
    Args:
        message: Message to display with spinner
    """
    import itertools
    import threading
    import time
    
    spinner = itertools.cycle(['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'])
    stop_spinner = threading.Event()
    
    def spin():
        while not stop_spinner.is_set():
            click.echo(f'\r{next(spinner)} {message}', nl=False)
            time.sleep(0.1)
        click.echo('\r' + ' ' * (len(message) + 2), nl=False)
        click.echo('\r', nl=False)
    
    spinner_thread = threading.Thread(target=spin)
    spinner_thread.daemon = True
    spinner_thread.start()
    
    return stop_spinner
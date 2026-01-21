"""CLI commands for managing and serving tools."""

import importlib
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
from typing import List, Optional

import httpx
import typer
from rich import print as rprint
from rich.console import Console
from rich.table import Table

from mindtrace.agents.toolkit import ToolkitLoader

tools_app = typer.Typer(
    name="tools",
    help="Manage and serve Mindtrace tools",
    no_args_is_help=True,
)

console = Console()


@tools_app.command("list")
def list_tools(
    toolkit: Optional[str] = typer.Argument(
        None,
        help="Specific toolkit to list tools from"
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show detailed information"
    ),
):
    """List available toolkits and their tools."""
    loader = ToolkitLoader()
    
    if toolkit:
        # List tools in a specific toolkit
        try:
            toolkit_meta = loader.load_toolkit(toolkit)
            
            rprint(f"\n[bold cyan]Toolkit:[/bold cyan] {toolkit_meta.name}")
            rprint(f"[bold]Description:[/bold] {toolkit_meta.description}")
            rprint(f"[bold]Version:[/bold] {toolkit_meta.version}")
            rprint(f"[bold]Tags:[/bold] {', '.join(toolkit_meta.tags)}")
            rprint(f"\n[bold green]Tools ({len(toolkit_meta.tools)}):[/bold green]\n")
            
            table = Table(show_header=True, header_style="bold magenta")
            table.add_column("Tool Name", style="cyan")
            table.add_column("Type", style="yellow")
            if verbose:
                table.add_column("Description", style="white")
            
            for tool in toolkit_meta.tools:
                tool_type = "async" if tool.is_async else "sync"
                if verbose:
                    desc = tool.description.split('\n')[0][:60]
                    table.add_row(tool.name, tool_type, desc)
                else:
                    table.add_row(tool.name, tool_type)
            
            console.print(table)
            
        except ImportError as e:
            rprint(f"[bold red]Error:[/bold red] Failed to load toolkit '{toolkit}': {e}")
            raise typer.Exit(code=1)
    
    else:
        # List all toolkits
        toolkits = loader.discover_toolkits()
        
        if not toolkits:
            rprint("[yellow]No toolkits found.[/yellow]")
            return
        
        rprint(f"\n[bold cyan]Available Toolkits ({len(toolkits)}):[/bold cyan]\n")
        
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Toolkit", style="cyan")
        table.add_column("Source", style="dim")
        table.add_column("Tools", style="yellow", justify="right")
        if verbose:
            table.add_column("Description", style="white")
        
        for toolkit_name in toolkits:
            try:
                toolkit_meta = loader.load_toolkit(toolkit_name)
                source = loader.get_toolkit_source(toolkit_name)
                source_label = "external" if source == "external" else "built-in"
                source_style = "green" if source == "external" else "blue"
                
                if verbose:
                    desc = toolkit_meta.description[:60]
                    table.add_row(
                        toolkit_name,
                        f"[{source_style}]{source_label}[/{source_style}]",
                        str(len(toolkit_meta.tools)),
                        desc
                    )
                else:
                    table.add_row(
                        toolkit_name,
                        f"[{source_style}]{source_label}[/{source_style}]",
                        str(len(toolkit_meta.tools))
                    )
            except ImportError:
                if verbose:
                    table.add_row(toolkit_name, "unknown", "Error", "Failed to load")
                else:
                    table.add_row(toolkit_name, "unknown", "Error")
        
        console.print(table)
        rprint("\n[dim]Use 'mindtrace tools list <toolkit>' to see tools in a specific toolkit[/dim]\n")


@tools_app.command("pull")
def pull_toolkit(
    toolkit: str = typer.Argument(..., help="Name of the toolkit to pull/verify"),
    package: Optional[str] = typer.Option(
        None,
        "--package",
        "-p",
        help="Package name to install from (e.g., 'external-tools' or 'git+https://github.com/user/repo.git')"
    ),
    install: bool = typer.Option(
        False,
        "--install",
        "-i",
        help="Install the package if not found (requires --package)"
    ),
):
    """Pull (verify) a toolkit and show its details.
    
    This command verifies that a toolkit can be loaded and shows its details.
    If the toolkit is not found and --package is provided, it can install it.
    
    Examples:
    
        # Pull built-in toolkit
        mindtrace tools pull basler_camera_tools
        
        # Pull from external package (must be installed)
        mindtrace tools pull external_tools --package external-tools
        
        # Install and pull from external package
        mindtrace tools pull external_tools --package external-tools --install
        
        # Install from GitHub and pull
        mindtrace tools pull my_tools --package git+https://github.com/user/tools.git --install
    """
    loader = ToolkitLoader()
    
    # If package is provided and install is requested, try to install it
    if package and install:
        rprint(f"\n[bold cyan]Installing package '{package}'...[/bold cyan]")
        try:
            import subprocess
            result = subprocess.run(
                ["pip", "install", package],
                capture_output=True,
                text=True,
                check=True
            )
            rprint(f"[green]✓[/green] Package '{package}' installed successfully\n")
        except subprocess.CalledProcessError as e:
            rprint(f"[bold red]Error:[/bold red] Failed to install package '{package}': {e.stderr}")
            raise typer.Exit(code=1)
        except FileNotFoundError:
            rprint(f"[bold red]Error:[/bold red] pip not found. Please install pip first.")
            raise typer.Exit(code=1)
    
    # Try to load the toolkit
    module_path = None
    if package:
        # If package is specified, try to construct module path
        # Common patterns: package_name -> package_name.tools
        # Or use the package name directly if it's a module
        possible_paths = [
            f"{package}.tools",
            f"{package}.toolkits",
            package,
        ]
        
        # Try each possible path
        for path in possible_paths:
            try:
                importlib.import_module(path)
                module_path = path
                break
            except ImportError:
                continue
        
        if not module_path:
            rprint(f"[yellow]Warning:[/yellow] Could not determine module path for package '{package}'")
            rprint(f"[dim]Tried: {', '.join(possible_paths)}[/dim]")
            rprint(f"[dim]You may need to specify the full module path manually[/dim]\n")
    
    with console.status(f"[bold green]Loading toolkit '{toolkit}'..."):
        try:
            toolkit_meta = loader.load_toolkit(toolkit, module_path=module_path)
        except ImportError as e:
            error_msg = str(e)
            if package:
                rprint(f"[bold red]Error:[/bold red] Failed to load toolkit '{toolkit}' from package '{package}': {error_msg}")
                rprint(f"\n[yellow]Suggestions:[/yellow]")
                rprint(f"  1. Ensure the package is installed: pip install {package}")
                rprint(f"  2. Check if the toolkit name is correct")
                rprint(f"  3. Verify the package structure matches expected format")
            else:
                rprint(f"[bold red]Error:[/bold red] Failed to load toolkit '{toolkit}': {error_msg}")
                rprint(f"\n[yellow]If this is an external toolkit, try:[/yellow]")
                rprint(f"  mindtrace tools pull {toolkit} --package <package_name>")
            raise typer.Exit(code=1)
    
    source = loader.get_toolkit_source(toolkit)
    source_label = "external" if source == "external" else "built-in"
    source_color = "green" if source == "external" else "blue"
    
    rprint(f"\n[bold green]✓[/bold green] Successfully loaded toolkit '{toolkit_meta.name}'")
    rprint(f"[{source_color}]Source: {source_label}[/{source_color}]")
    rprint(f"\n[bold]Details:[/bold]")
    rprint(f"  Name: {toolkit_meta.name}")
    rprint(f"  Description: {toolkit_meta.description}")
    rprint(f"  Version: {toolkit_meta.version}")
    rprint(f"  Tags: {', '.join(toolkit_meta.tags)}")
    rprint(f"  Module: {toolkit_meta.module_name}")
    rprint(f"  Tools: {len(toolkit_meta.tools)}")
    
    if toolkit_meta.tools:
        rprint("\n[bold]Available Tools:[/bold]")
        for tool in toolkit_meta.tools:
            tool_type = "async" if tool.is_async else "sync"
            rprint(f"  - {tool.name} ({tool_type})")
    
    rprint(f"\n[bold green]✓[/bold green] Toolkit is ready to use!\n")


@tools_app.command("serve")
def serve_tools(
    toolkits: List[str] = typer.Argument(
        ...,
        help="One or more toolkit names to serve"
    ),
    name: str = typer.Option(
        ...,
        "--name",
        "-n",
        help="Name for this tool server (required for registry tracking)"
    ),
    tags: Optional[List[str]] = typer.Option(
        None,
        "--tags",
        "-t",
        help="Filter tools by tags (can specify multiple)"
    ),
    host: str = typer.Option(
        "0.0.0.0",
        "--host",
        "-h",
        help="Host to bind the server to"
    ),
    port: int = typer.Option(
        8000,
        "--port",
        "-p",
        help="Port to bind the server to"
    ),
    workers: int = typer.Option(
        1,
        "--workers",
        "-w",
        help="Number of worker processes (use >1 for production)"
    ),
):
    """Serve tools over MCP using Service infrastructure.
    
    Launches a ToolService as a detached background process with:
    - Multiple worker processes (Gunicorn/Uvicorn)
    - Structured logging to files
    - Graceful shutdown handling
    - Status and heartbeat endpoints
    - Persistent MCP server
    - Registry tracking (name is required)
    
    The service runs in the background and survives after this command exits.
    
    Examples:
    
        # Serve basler_camera_tools with a name (required)
        mindtrace tools serve basler_camera_tools --name camera-server
        
        # Serve multiple toolkits with 4 workers for production
        mindtrace tools serve basler_camera_tools labelstudio_tools --workers 4 --name production-server
        
        # Serve only camera-tagged tools
        mindtrace tools serve basler_camera_tools --tags camera --name camera-tools
        
        # Custom host and port
        mindtrace tools serve basler_camera_tools --host 0.0.0.0 --port 8080 --name my-server
        
    Stopping the server:
        mindtrace tools stop --name camera-server
        # or
        mindtrace tools stop --port 8000
    """
    from mindtrace.agents.server.tool_service import ToolService
    from mindtrace.registry import Registry
    
    rprint(f"\n[bold cyan]Mindtrace Tool Service[/bold cyan]")
    rprint(f"[dim]Launching with toolkits: {', '.join(toolkits)}[/dim]")
    
    if tags:
        rprint(f"[yellow]Filtering by tags:[/yellow] {', '.join(tags)}")
    
    if workers > 1:
        rprint(f"[cyan]Workers:[/cyan] {workers}")
    
    rprint()  # blank line
    
    try:
        # Convert tags list to set
        tag_set = set(tags) if tags else None
        
        # Import ToolService to get config paths
        from mindtrace.agents.server.tool_service import ToolService
        
        # Check if a server with the same name already exists
        try:
            registry = Registry()
            registry_key = f"toolservers:{name}"
            existing_info = registry.load(registry_key)
            existing_pid = existing_info.get("pid")
            existing_host = existing_info.get("host", "0.0.0.0")
            existing_port = existing_info.get("port", 8000)
            
            # Check if the existing server is still running
            is_running = False
            if existing_pid:
                try:
                    import psutil
                    process_check = psutil.Process(existing_pid)
                    if process_check.is_running():
                        is_running = True
                except (psutil.NoSuchProcess, psutil.AccessDenied, ImportError):
                    # Process doesn't exist or psutil not available
                    is_running = False
            
            if is_running:
                # Server is running - stop it first
                rprint(f"[yellow]⚠[/yellow] Server '{name}' is already running (PID: {existing_pid})")
                rprint(f"[dim]Stopping existing server...[/dim]")
                
                # Try to stop via shutdown endpoint
                try:
                    shutdown_url = f"http://{existing_host if existing_host != '0.0.0.0' else '127.0.0.1'}:{existing_port}/shutdown"
                    with httpx.Client(timeout=5.0) as client:
                        response = client.post(shutdown_url)
                        if response.status_code in [200, 202]:
                            rprint(f"[green]✓[/green] Stopped existing server")
                            # Wait a moment for process to fully stop
                            import time
                            time.sleep(1)
                        else:
                            rprint(f"[yellow]⚠[/yellow] Shutdown endpoint returned {response.status_code}")
                except Exception as e:
                    rprint(f"[yellow]⚠[/yellow] Could not stop via shutdown endpoint: {e}")
                    rprint(f"[dim]Attempting to kill process {existing_pid}...[/dim]")
                    try:
                        import psutil
                        process_check = psutil.Process(existing_pid)
                        process_check.terminate()
                        process_check.wait(timeout=5)
                        rprint(f"[green]✓[/green] Stopped existing server")
                    except Exception as e2:
                        rprint(f"[bold red]Error:[/bold red] Could not stop existing server: {e2}")
                        rprint(f"[yellow]Please stop it manually:[/yellow] mindtrace tools stop --name {name}")
                        raise typer.Exit(code=1)
                
                # Remove from registry
                try:
                    registry.delete(registry_key)
                except Exception:
                    pass
            else:
                # Server is stopped - clean it up
                rprint(f"[yellow]⚠[/yellow] Found stopped server '{name}' in registry, cleaning up...")
                try:
                    registry.delete(registry_key)
                    rprint(f"[green]✓[/green] Cleaned up stopped server entry")
                except Exception as e:
                    rprint(f"[yellow]⚠[/yellow] Failed to remove old entry: {e}")
                    
        except Exception:
            # No existing entry, that's fine - proceed normally
            pass
        
        # ToDo: add check if port is available
        
        rprint(f"[dim]Launching detached process...[/dim]")
        
        # Build launcher command (following hardware pattern)
        cmd = [
            sys.executable,
            "-m",
            "mindtrace.agents.server.tool_service_launcher",
            "--host", host,
            "--port", str(port),
            "--workers", str(workers),
            "--toolkits", ",".join(toolkits),
        ]
        
        if tag_set:
            cmd.extend(["--tags", ",".join(tag_set)])
        
        if name:
            cmd.extend(["--server-name", name])
        
        # Launch launcher module in a detached subprocess (following hardware pattern)
        # Redirect stdout/stderr to /dev/null since Service handles its own logging
        devnull = os.open(os.devnull, os.O_RDWR)
        try:
            process = subprocess.Popen(
                cmd,
                stdout=devnull,
                stderr=devnull,
                start_new_session=True,  # Detach from terminal session (like hardware)
                cwd=os.getcwd(),
            )
        finally:
            os.close(devnull)
        
        # Generate server_id for registry tracking
        server_id = uuid.uuid1()
        
        # Wait a moment to see if process crashes immediately
        import time
        time.sleep(2)
        
        # Check if process is still running
        try:
            return_code = process.poll()
            if return_code is not None:
                rprint(f"[bold red]Error:[/bold red] Server process exited immediately with code {return_code}")
                rprint(f"[yellow]The server may have failed to start. Check logs for details.[/yellow]")
                raise typer.Exit(code=1)
        except Exception as e:
            rprint(f"[bold red]Error:[/bold red] Failed to check process status: {e}")
            raise typer.Exit(code=1)
        
        # Verify server is up by checking /status endpoint
        rprint(f"[dim]Verifying server is up at {host}:{port}...[/dim]")
        
        # Build status URL
        status_host = host if host != "0.0.0.0" else "127.0.0.1"
        status_url = f"http://{status_host}:{port}/status"
        
        try:
            with httpx.Client(timeout=2.0) as client:
                response = client.post(status_url)
                if response.status_code in [200, 202]:
                    rprint(f"[green]✓[/green] Server is up and responding at {status_url}")
                else:
                    rprint(f"[yellow]⚠[/yellow] Server responded with status {response.status_code}")
        except (httpx.ConnectError, httpx.TimeoutException, httpx.RequestError):
            # Check if process is still running
            if process.poll() is None:
                rprint(f"[yellow]⚠[/yellow] Server process is running but not responding on port {port}")
                rprint(f"[yellow]The server may still be starting. Check logs or try:[/yellow]")
                rprint(f"[dim]  mindtrace tools list-servers[/dim]")
            else:
                rprint(f"[bold red]Error:[/bold red] Server process has stopped")
                rprint(f"[yellow]The server failed to start. Check logs for details.[/yellow]")
                raise typer.Exit(code=1)
        except Exception as e:
            rprint(f"[yellow]⚠[/yellow] Could not verify server status: {e}")
        

        
        # Save server info to registry
        try:
            registry = Registry()
            server_info = {
                "name": name,
                "host": host,
                "port": port,
                "pid": process.pid,  # PID of the launcher process
                "server_id": str(server_id),
                "toolkits": toolkits,
                "tags": list(tag_set) if tag_set else None,
                "workers": workers,
                "url": f"http://{host}:{port}/",
                "mcp_endpoint": f"http://{host}:{port}/mcp-server/mcp/",
                "status_endpoint": f"http://{host}:{port}/status",
            }
            registry_key = f"toolservers:{name}"
            registry.save(registry_key, server_info)
            rprint(f"[green]✓[/green] Server registered as '{name}' in registry")
        except Exception as e:
            rprint(f"[yellow]⚠[/yellow] Failed to save to registry: {e}")
            rprint(f"[dim]Server is running but not tracked in registry[/dim]")
        
        rprint(f"[bold green]✓ ToolService launched successfully![/bold green]")
        rprint(f"\n[cyan]Server Details:[/cyan]")
        rprint(f"  Name: {name}")
        rprint(f"  PID: {process.pid}")
        rprint(f"  Host: http://{host}:{port}")
        rprint(f"  MCP endpoint: http://{host}:{port}/mcp-server/mcp/")
        rprint(f"  Status: http://{host}:{port}/status")
        
        rprint(f"\n[yellow]Server is running in background[/yellow]")
        rprint(f"[dim]To stop the server:[/dim]")
        rprint(f"  mindtrace tools stop --name {name}")
        rprint(f"  [dim]or[/dim]  mindtrace tools stop --port {port}")
        if host != "0.0.0.0":
            rprint(f"  [dim]or[/dim]  mindtrace tools stop --host {host} --port {port}")
        rprint()
        
    except ImportError as e:
        rprint(f"\n[bold red]Error:[/bold red] Failed to load toolkit: {e}")
        raise typer.Exit(code=1)
    except Exception as e:
        rprint(f"\n[bold red]Error:[/bold red] {e}")
        import traceback
        rprint(f"[dim]{traceback.format_exc()}[/dim]")
        raise typer.Exit(code=1)


@tools_app.command("info")
def toolkit_info(
    toolkit: str = typer.Argument(..., help="Name of the toolkit"),
    tool: Optional[str] = typer.Option(
        None,
        "--tool",
        "-t",
        help="Show info for a specific tool"
    ),
):
    """Show detailed information about a toolkit or tool."""
    loader = ToolkitLoader()
    
    try:
        toolkit_meta = loader.load_toolkit(toolkit)
    except ImportError as e:
        rprint(f"[bold red]Error:[/bold red] Failed to load toolkit '{toolkit}': {e}")
        raise typer.Exit(code=1)
    
    if tool:
        # Show info for a specific tool
        tool_meta = toolkit_meta.get_tool(tool)
        if not tool_meta:
            rprint(f"[bold red]Error:[/bold red] Tool '{tool}' not found in toolkit '{toolkit}'")
            raise typer.Exit(code=1)
        
        rprint(f"\n[bold cyan]Tool:[/bold cyan] {tool_meta.name}")
        rprint(f"[bold]Toolkit:[/bold] {toolkit_meta.name}")
        rprint(f"[bold]Type:[/bold] {'async' if tool_meta.is_async else 'sync'}")
        rprint(f"[bold]Tags:[/bold] {', '.join(tool_meta.tags)}")
        rprint(f"\n[bold]Description:[/bold]")
        rprint(tool_meta.description)
        
    else:
        # Show info for the toolkit
        rprint(f"\n[bold cyan]Toolkit:[/bold cyan] {toolkit_meta.name}")
        rprint(f"[bold]Version:[/bold] {toolkit_meta.version}")
        rprint(f"[bold]Tags:[/bold] {', '.join(toolkit_meta.tags)}")
        rprint(f"[bold]Module:[/bold] {toolkit_meta.module_name}")
        rprint(f"\n[bold]Description:[/bold]")
        rprint(toolkit_meta.description)
        rprint(f"\n[bold]Tools ({len(toolkit_meta.tools)}):[/bold]")
        for t in toolkit_meta.tools:
            tool_type = "async" if t.is_async else "sync"
            rprint(f"  - {t.name} ({tool_type})")


@tools_app.command("stop")
def stop_server(
    name: Optional[str] = typer.Option(
        None,
        "--name",
        "-n",
        help="Name of the server to stop (from registry)"
    ),
    host: Optional[str] = typer.Option(
        None,
        "--host",
        "-h",
        help="Host of the server to stop (ignored if --name is provided)"
    ),
    port: Optional[int] = typer.Option(
        None,
        "--port",
        "-p",
        help="Port of the server to stop (ignored if --name is provided)"
    ),
    url: Optional[str] = typer.Option(
        None,
        "--url",
        "-u",
        help="Full URL to the server (overrides host and port)"
    ),
):
    """Stop a running MCP tool server by sending shutdown request.
    
    Can stop by server name (from registry), host/port, or URL.
    
    Examples:
    
        # Stop by server name (from registry)
        mindtrace tools stop --name camera-server
        
        # Stop default server (0.0.0.0:8000)
        mindtrace tools stop
        
        # Stop server on specific port
        mindtrace tools stop --port 8080
        
        # Stop server on specific host and port
        mindtrace tools stop --host localhost --port 8000
        
        # Stop server using full URL
        mindtrace tools stop --url http://localhost:8000
    """
    from mindtrace.registry import Registry
    
    rprint(f"\n[bold cyan]Stopping MCP Tool Server[/bold cyan]\n")
    
    # If name is provided, load server info from registry
    if name:
        try:
            registry = Registry()
            registry_key = f"toolservers:{name}"
            server_info = registry.load(registry_key)
            
            # Override host/port with registry values
            host = server_info.get("host", host or "0.0.0.0")
            port = server_info.get("port", port or 8000)
            pid = server_info.get("pid")
            pid_file = server_info.get("pid_file")
            
            rprint(f"[dim]Found server '{name}' in registry[/dim]")
            rprint(f"[dim]Host: {host}, Port: {port}, PID: {pid}[/dim]\n")
            
            # Try to verify process is still running
            if pid:
                try:
                    import psutil
                    process = psutil.Process(pid)
                    if not process.is_running():
                        rprint(f"[yellow]⚠ Process {pid} is not running. Server may have stopped.[/yellow]")
                        # Remove from registry
                        try:
                            registry.delete(registry_key)
                            rprint(f"[green]✓ Removed '{name}' from registry[/green]")
                        except:
                            pass
                        raise typer.Exit(code=1)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    rprint(f"[yellow]⚠ Process {pid} not found. Server may have stopped.[/yellow]")
                    # Remove from registry
                    try:
                        registry.delete(registry_key)
                        rprint(f"[green]✓ Removed '{name}' from registry[/green]")
                    except:
                        pass
                    raise typer.Exit(code=1)
                except ImportError:
                    # psutil not available, skip process check
                    pass
                    
        except Exception as e:
            rprint(f"[bold red]Error:[/bold red] Failed to load server '{name}' from registry: {e}")
            rprint(f"[dim]Try stopping by port: mindtrace tools stop --port <port>[/dim]")
            raise typer.Exit(code=1)
    else:
        # Use defaults if not provided
        host = host or "0.0.0.0"
        port = port or 8000
    
    # Build the shutdown URL
    if url:
        shutdown_url = f"{url.rstrip('/')}/shutdown"
        display_url = url
    else:
        shutdown_url = f"http://{host}:{port}/shutdown"
        display_url = f"{host}:{port}"
    
    rprint(f"[dim]Sending shutdown request to {shutdown_url}...[/dim]\n")
    
    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.post(shutdown_url)
            
            if response.status_code in [200, 202]:
                rprint(f"[bold green]✓ Server at {display_url} stopped successfully![/bold green]")
                rprint(f"[dim]Response: {response.text[:200]}[/dim]")
                
                # Remove from registry if stopped by name
                if name:
                    try:
                        registry = Registry()
                        registry_key = f"toolservers:{name}"
                        registry.delete(registry_key)
                        rprint(f"[green]✓ Removed '{name}' from registry[/green]")
                    except Exception as e:
                        rprint(f"[yellow]⚠ Failed to remove from registry: {e}[/yellow]")
            else:
                rprint(f"[yellow]⚠ Server responded with status {response.status_code}[/yellow]")
                rprint(f"[dim]Response: {response.text[:200]}[/dim]")
                raise typer.Exit(code=1)
                
    except httpx.ConnectError:
        rprint(f"[red]✗ Could not connect to server at {display_url}[/red]")
        rprint(f"[dim]Server may not be running or address is incorrect[/dim]")
        raise typer.Exit(code=1)
    except httpx.TimeoutException:
        rprint(f"[yellow]⚠ Request to {display_url} timed out[/yellow]")
        rprint(f"[dim]Server may be unresponsive[/dim]")
        raise typer.Exit(code=1)
    except Exception as e:
        rprint(f"[red]✗ Error stopping server: {e}[/red]")
        raise typer.Exit(code=1)
    
    rprint()


@tools_app.command("list-servers")
def list_servers(
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show detailed information about each server"
    ),
):
    """List all registered tool servers from the registry.
    
    Shows all tool servers that were started with --name and saved to the registry.
    
    Examples:
    
        # List all registered servers
        mindtrace tools list-servers
        
        # Show detailed information
        mindtrace tools list-servers --verbose
    """
    from mindtrace.registry import Registry
    import psutil
    
    rprint(f"\n[bold cyan]Registered Tool Servers[/bold cyan]\n")
    
    try:
        registry = Registry()
        
        # List all objects in registry
        all_objects = registry.list_objects()
        
        # Filter for toolservers
        toolserver_keys = [obj for obj in all_objects if obj.startswith("toolservers:")]
        
        if not toolserver_keys:
            rprint("[yellow]No registered tool servers found.[/yellow]")
            rprint("[dim]Start a server with --name to register it:[/dim]")
            rprint("[dim]  mindtrace tools serve basler_camera_tools --name my-server[/dim]\n")
            return
        
        # Load and display server info
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Name", style="cyan")
        table.add_column("Host", style="white")
        table.add_column("Port", style="yellow", justify="right")
        table.add_column("Status", style="green")
        if verbose:
            table.add_column("PID", style="dim", justify="right")
            table.add_column("Toolkits", style="white")
            table.add_column("Workers", style="dim", justify="right")
        
        active_count = 0
        inactive_count = 0
        
        for key in sorted(toolserver_keys):
            try:
                server_info = registry.load(key)
                server_name = server_info.get("name", key.replace("toolservers:", ""))
                host = server_info.get("host", "unknown")
                port = server_info.get("port", "unknown")
                pid = server_info.get("pid")
                toolkits = server_info.get("toolkits", [])
                workers = server_info.get("workers", 1)
                
                # Check if process is running
                status = "unknown"
                status_style = "yellow"
                if pid:
                    try:
                        process = psutil.Process(pid)
                        if process.is_running():
                            status = "running"
                            status_style = "green"
                            active_count += 1
                        else:
                            status = "stopped"
                            status_style = "red"
                            inactive_count += 1
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        status = "stopped"
                        status_style = "red"
                        inactive_count += 1
                    except ImportError:
                        status = "unknown"
                        status_style = "yellow"
                else:
                    inactive_count += 1
                    status = "no PID"
                    status_style = "yellow"
                
                if verbose:
                    toolkits_str = ", ".join(toolkits[:2])
                    if len(toolkits) > 2:
                        toolkits_str += f" (+{len(toolkits) - 2})"
                    table.add_row(
                        server_name,
                        host,
                        str(port),
                        f"[{status_style}]{status}[/{status_style}]",
                        str(pid) if pid else "N/A",
                        toolkits_str,
                        str(workers)
                    )
                else:
                    table.add_row(
                        server_name,
                        host,
                        str(port),
                        f"[{status_style}]{status}[/{status_style}]"
                    )
                    
            except Exception as e:
                # Skip corrupted entries
                if verbose:
                    table.add_row(
                        key.replace("toolservers:", ""),
                        "error",
                        "error",
                        "[red]error[/red]",
                        "N/A",
                        str(e)[:30],
                        "N/A"
                    )
        
        console.print(table)
        
        rprint(f"\n[dim]Total: {len(toolserver_keys)} server(s) - {active_count} active, {inactive_count} inactive[/dim]")
        rprint(f"[dim]Use 'mindtrace tools stop --name <name>' to stop a server[/dim]\n")
        
    except Exception as e:
        rprint(f"[bold red]Error:[/bold red] Failed to list servers: {e}")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    tools_app()


"""Process management for hardware services."""

import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import psutil


class ProcessManager:
    """Manages hardware service processes."""

    def __init__(self):
        """Initialize process manager."""
        self.home_dir = Path.home() / ".mindtrace"
        self.home_dir.mkdir(exist_ok=True)
        self.pid_file = self.home_dir / "hw_services.json"
        self.processes: Dict[str, Any] = {}
        self.load_pids()

    def load_pids(self):
        """Load saved PIDs from file."""
        if self.pid_file.exists():
            try:
                with open(self.pid_file, "r") as f:
                    self.processes = json.load(f)
                # Clean up dead processes
                self._cleanup_dead_processes()
            except (json.JSONDecodeError, IOError):
                self.processes = {}
        else:
            self.processes = {}

    def save_pids(self):
        """Save PIDs to file."""
        with open(self.pid_file, "w") as f:
            json.dump(self.processes, f, indent=2)

    def _cleanup_dead_processes(self):
        """Remove entries for processes that are no longer running."""
        dead_services = []
        for service_name, info in self.processes.items():
            if not self._is_process_running(info["pid"]):
                dead_services.append(service_name)

        for service in dead_services:
            del self.processes[service]

        if dead_services:
            self.save_pids()

    def _is_process_running(self, pid: int) -> bool:
        """Check if a process with given PID is running."""
        try:
            process = psutil.Process(pid)
            return process.is_running()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return False

    def start_camera_api(self, host: str = None, port: int = None, include_mocks: bool = False) -> subprocess.Popen:
        """Launch camera API service.

        Args:
            host: Host to bind the service to (default: CAMERA_API_HOST env var or 'localhost')
            port: Port to run the service on (default: CAMERA_API_PORT env var or 8002)
            include_mocks: Include mock cameras in discovery

        Returns:
            The subprocess handle
        """
        # Use environment variables as defaults
        if host is None:
            host = os.getenv("CAMERA_API_HOST", "localhost")
        if port is None:
            port = int(os.getenv("CAMERA_API_PORT", "8002"))
        # Build command
        cmd = [sys.executable, "-m", "mindtrace.hardware.api.cameras.launcher", "--host", host, "--port", str(port)]

        if include_mocks:
            cmd.append("--include-mocks")

        # Set Camera API environment variables for other services to use
        os.environ["CAMERA_API_HOST"] = host
        os.environ["CAMERA_API_PORT"] = str(port)
        os.environ["CAMERA_API_URL"] = f"http://{host}:{port}"

        # Start process
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,  # Create new process group
        )

        # Wait a moment to ensure it started
        time.sleep(1)

        # Check if process is still running
        if process.poll() is not None:
            raise RuntimeError(f"Failed to start camera API service on {host}:{port}")

        # Save process info
        self.processes["camera_api"] = {
            "pid": process.pid,
            "host": host,
            "port": port,
            "start_time": datetime.now().isoformat(),
            "command": " ".join(cmd),
        }
        self.save_pids()

        return process

    def start_plc_api(self, host: str = None, port: int = None) -> subprocess.Popen:
        """Launch PLC API service.

        Args:
            host: Host to bind the service to (default: PLC_API_HOST env var or 'localhost')
            port: Port to run the service on (default: PLC_API_PORT env var or 8003)

        Returns:
            The subprocess handle
        """
        # Use environment variables as defaults
        if host is None:
            host = os.getenv("PLC_API_HOST", "localhost")
        if port is None:
            port = int(os.getenv("PLC_API_PORT", "8003"))

        # Build command
        cmd = [sys.executable, "-m", "mindtrace.hardware.api.plcs.launcher", "--host", host, "--port", str(port)]

        # Set PLC API environment variables for other services to use
        os.environ["PLC_API_HOST"] = host
        os.environ["PLC_API_PORT"] = str(port)
        os.environ["PLC_API_URL"] = f"http://{host}:{port}"

        # Start process
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,  # Create new process group
        )

        # Wait a moment to ensure it started
        time.sleep(1)

        # Check if process is still running
        if process.poll() is not None:
            raise RuntimeError(f"Failed to start PLC API service on {host}:{port}")

        # Save process info
        self.processes["plc_api"] = {
            "pid": process.pid,
            "host": host,
            "port": port,
            "start_time": datetime.now().isoformat(),
            "command": " ".join(cmd),
        }
        self.save_pids()

        return process

    def start_configurator(self, host: str = None, port: int = None, backend_port: int = None) -> subprocess.Popen:
        """Launch camera configurator app.

        Args:
            host: Host to bind the app to (default: CAMERA_UI_HOST env var or 'localhost')
            port: Port to run the app on - frontend (default: CAMERA_UI_FRONTEND_PORT env var or 3000)
            backend_port: Port for Reflex backend (default: CAMERA_UI_BACKEND_PORT env var or 8000)

        Returns:
            The subprocess handle
        """
        # Use environment variables as defaults
        if host is None:
            host = os.getenv("CAMERA_UI_HOST", "localhost")
        if port is None:
            port = int(os.getenv("CAMERA_UI_FRONTEND_PORT", "3000"))
        if backend_port is None:
            backend_port = int(os.getenv("CAMERA_UI_BACKEND_PORT", "8000"))
        # Find app directory
        app_dir = Path(__file__).parent.parent.parent / "apps" / "camera_configurator"

        if not app_dir.exists():
            raise RuntimeError(f"Camera configurator app not found at {app_dir}")

        # Note: API URL is configured via environment variables in rxconfig.py

        # Build command - use uv run reflex run for Reflex apps
        cmd = ["uv", "run", "reflex", "run", "--frontend-port", str(port), "--backend-port", str(backend_port)]

        # Set environment for subprocess - need host and ports for config to work correctly
        env = os.environ.copy()
        env["CAMERA_UI_HOST"] = host  # Host for UI service
        env["CAMERA_UI_FRONTEND_PORT"] = str(port)  # Frontend port for rxconfig.py
        env["CAMERA_UI_BACKEND_PORT"] = str(backend_port)  # Backend port for rxconfig.py

        # Debug: Print command and environment
        print(f"DEBUG: Command: {' '.join(cmd)}")
        print(f"DEBUG: Working directory: {app_dir}")
        print(f"DEBUG: CAMERA_API_HOST in env: {env.get('CAMERA_API_HOST', 'NOT SET')}")
        print(f"DEBUG: CAMERA_API_PORT in env: {env.get('CAMERA_API_PORT', 'NOT SET')}")
        print(f"DEBUG: CAMERA_API_URL in env: {env.get('CAMERA_API_URL', 'NOT SET')}")
        print(f"DEBUG: CAMERA_UI_HOST in env: {env.get('CAMERA_UI_HOST', 'NOT SET')}")
        print(f"DEBUG: CAMERA_UI_FRONTEND_PORT in env: {env.get('CAMERA_UI_FRONTEND_PORT', 'NOT SET')}")
        print(f"DEBUG: CAMERA_UI_BACKEND_PORT in env: {env.get('CAMERA_UI_BACKEND_PORT', 'NOT SET')}")

        # Start process - allow output to show for debugging
        process = subprocess.Popen(cmd, cwd=str(app_dir), env=env, start_new_session=True)

        # Wait a moment to ensure it started
        time.sleep(2)

        # Check if process is still running
        if process.poll() is not None:
            raise RuntimeError(f"Failed to start configurator app on {host}:{port}")

        # Save process info
        self.processes["configurator"] = {
            "pid": process.pid,
            "host": host,
            "port": port,
            "backend_port": backend_port,
            "start_time": datetime.now().isoformat(),
            "command": " ".join(cmd),
            "app_dir": str(app_dir),  # Save for cleanup
        }
        self.save_pids()

        return process

    def stop_service(self, service_name: str) -> bool:
        """Stop a service by name.

        Args:
            service_name: Name of the service to stop

        Returns:
            True if stopped successfully
        """
        if service_name not in self.processes:
            return False

        info = self.processes[service_name]
        pid = info["pid"]

        try:
            # Special handling for configurator (Reflex app)
            if service_name == "configurator":
                self._stop_reflex_app(info)
            else:
                # Standard process termination
                self._stop_process(pid)

            # Remove from tracking
            del self.processes[service_name]
            self.save_pids()
            return True

        except (ProcessLookupError, PermissionError):
            # Process already dead or no permission
            if service_name in self.processes:
                del self.processes[service_name]
                self.save_pids()
            return True

    def _stop_process(self, pid: int):
        """Stop a single process gracefully."""
        # First try graceful termination
        os.kill(pid, signal.SIGTERM)

        # Wait up to 5 seconds for graceful shutdown
        for _ in range(50):
            if not self._is_process_running(pid):
                break
            time.sleep(0.1)

        # If still running, force kill
        if self._is_process_running(pid):
            os.kill(pid, signal.SIGKILL)
            time.sleep(0.5)

    def _stop_reflex_app(self, info: Dict[str, Any]):
        """Stop Reflex app and all related processes (Next.js, bun, node)."""
        pid = info["pid"]
        app_dir = info.get("app_dir")

        # 1. Stop main Reflex process
        self._stop_process(pid)

        # 2. Find and kill related Reflex processes
        try:
            # Get all processes and find Reflex-related ones
            for proc in psutil.process_iter(["pid", "name", "cmdline", "cwd"]):
                try:
                    proc_info = proc.info
                    cmdline = proc_info.get("cmdline", [])
                    name = proc_info.get("name", "")
                    cwd = proc_info.get("cwd", "")

                    # Skip if we can't get process info
                    if not cmdline:
                        continue

                    cmdline_str = " ".join(cmdline).lower()

                    # Kill processes related to our Reflex app
                    should_kill = False

                    # Check for Reflex-specific processes
                    if any(
                        pattern in cmdline_str
                        for pattern in ["reflex", "rx", "camera_configurator", "camera-configurator"]
                    ):
                        should_kill = True

                    # Check for Next.js/Node processes in our app directory
                    elif app_dir and cwd and app_dir in cwd:
                        if any(pattern in name.lower() for pattern in ["node", "npm", "bun", "next"]):
                            should_kill = True

                    # Check for processes on our ports
                    elif any(
                        pattern in cmdline_str
                        for pattern in [f":{info.get('port', 3000)}", f":{info.get('backend_port', 8000)}"]
                    ):
                        should_kill = True

                    if should_kill and proc.pid != os.getpid():  # Don't kill ourselves
                        try:
                            proc.terminate()
                            # Wait briefly for graceful termination
                            proc.wait(timeout=2)
                        except (psutil.NoSuchProcess, psutil.TimeoutExpired):
                            try:
                                proc.kill()  # Force kill if terminate didn't work
                            except psutil.NoSuchProcess:
                                pass  # Already dead
                        except psutil.AccessDenied:
                            pass  # Can't kill, skip

                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    # Process disappeared or no access, skip
                    continue

        except Exception:
            # If cleanup fails, at least the main process should be stopped
            pass

    def stop_all(self):
        """Stop all running services."""
        services = list(self.processes.keys())
        # Stop configurator first (depends on API)
        if "configurator" in services:
            self.stop_service("configurator")
            services.remove("configurator")

        # Stop remaining services
        for service in services:
            self.stop_service(service)

    def get_status(self) -> Dict[str, Any]:
        """Get status of all services.

        Returns:
            Dictionary with service status information
        """
        status = {}

        for service_name, info in self.processes.items():
            pid = info["pid"]
            is_running = self._is_process_running(pid)

            service_status = {
                "running": is_running,
                "pid": pid,
                "host": info.get("host", "unknown"),
                "port": info.get("port", 0),
                "start_time": info.get("start_time", "unknown"),
            }

            if is_running:
                try:
                    process = psutil.Process(pid)
                    # Calculate uptime
                    start_timestamp = process.create_time()
                    uptime_seconds = time.time() - start_timestamp
                    hours, remainder = divmod(int(uptime_seconds), 3600)
                    minutes, seconds = divmod(remainder, 60)

                    if hours > 0:
                        service_status["uptime"] = f"{hours}h {minutes}m {seconds}s"
                    elif minutes > 0:
                        service_status["uptime"] = f"{minutes}m {seconds}s"
                    else:
                        service_status["uptime"] = f"{seconds}s"

                    # Memory usage
                    mem_info = process.memory_info()
                    service_status["memory_mb"] = round(mem_info.rss / 1024 / 1024, 1)

                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            status[service_name] = service_status

        return status

    def is_service_running(self, service_name: str) -> bool:
        """Check if a specific service is running.

        Args:
            service_name: Name of the service

        Returns:
            True if the service is running
        """
        if service_name not in self.processes:
            return False

        return self._is_process_running(self.processes[service_name]["pid"])

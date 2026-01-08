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

        # Start process (use DEVNULL to avoid pipe buffer overflow)
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
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

        # Start process (use DEVNULL to avoid pipe buffer overflow)
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
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

    def start_stereo_camera_api(self, host: str = None, port: int = None) -> subprocess.Popen:
        """Launch Stereo Camera API service.

        Args:
            host: Host to bind the service to (default: STEREO_CAMERA_API_HOST env var or 'localhost')
            port: Port to run the service on (default: STEREO_CAMERA_API_PORT env var or 8004)

        Returns:
            The subprocess handle
        """
        # Use environment variables as defaults
        if host is None:
            host = os.getenv("STEREO_CAMERA_API_HOST", "localhost")
        if port is None:
            port = int(os.getenv("STEREO_CAMERA_API_PORT", "8004"))

        # Build command
        cmd = [
            sys.executable,
            "-m",
            "mindtrace.hardware.api.stereo_cameras.launcher",
            "--host",
            host,
            "--port",
            str(port),
        ]

        # Set Stereo Camera API environment variables for other services to use
        os.environ["STEREO_CAMERA_API_HOST"] = host
        os.environ["STEREO_CAMERA_API_PORT"] = str(port)
        os.environ["STEREO_CAMERA_API_URL"] = f"http://{host}:{port}"

        # Start process (use DEVNULL to avoid pipe buffer overflow)
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,  # Create new process group
        )

        # Wait a moment to ensure it started
        time.sleep(1)

        # Check if process is still running
        if process.poll() is not None:
            raise RuntimeError(f"Failed to start Stereo Camera API service on {host}:{port}")

        # Save process info
        self.processes["stereo_camera_api"] = {
            "pid": process.pid,
            "host": host,
            "port": port,
            "start_time": datetime.now().isoformat(),
            "command": " ".join(cmd),
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

    def stop_all(self):
        """Stop all running services."""
        services = list(self.processes.keys())
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

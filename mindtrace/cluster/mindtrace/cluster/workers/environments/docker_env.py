import os
from typing import Dict, List, Optional

import docker
import docker.types
from docker.errors import DockerException

from mindtrace.core import Mindtrace


class DockerEnvironment(Mindtrace):
    """Manages Docker-based environments for workers."""

    def __init__(
        self,
        image: str,
        environment: Optional[Dict[str, str]] = None,
        volumes: Optional[Dict[str, Dict[str, str]]] = None,
        devices: Optional[List[str]] = None,
        working_dir: Optional[str] = None,
        ports: Optional[dict[int | str, int | str]] = None,
        **kwargs,
    ):
        super().__init__()
        self.image = image
        self.environment = environment or {}
        self.volumes = volumes or {}
        gcp_creds = self.environment.get("GOOGLE_APPLICATION_CREDENTIALS") or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        if gcp_creds:
            self.volumes[gcp_creds] = {
                "bind": "/tmp/keys/gcp_service_acc_key.json",
                "mode": "ro",
            }
            self.environment["GOOGLE_APPLICATION_CREDENTIALS"] = "/tmp/keys/gcp_service_acc_key.json"
        self.devices = devices if devices else []
        self.working_dir = working_dir
        self.container = None
        self.ports = ports or {}
        self.client = docker.from_env()
        self.kwargs = kwargs

    def setup(self, pull=True, command=None) -> str:
        """Setup Docker container environment.

        Returns:
            str: Container ID
        """
        try:
            # Pull image if not exists
            if pull:
                self.client.images.pull(self.image)
            if command is None:
                command = "sh"
            if self.devices:
                # Create and start container
                self.container = self.client.containers.run(
                    image=self.image,
                    environment=self.environment,
                    volumes=self.volumes,
                    working_dir=self.working_dir,
                    device_requests=[docker.types.DeviceRequest(device_ids=self.devices, capabilities=[["gpu"]])],
                    detach=True,
                    tty=True,
                    command=command,
                    stdin_open=True,
                    ports=self.ports,
                    **self.kwargs,
                )
            else:
                self.container = self.client.containers.run(
                    image=self.image,
                    environment=self.environment,
                    volumes=self.volumes,
                    working_dir=self.working_dir,
                    detach=True,
                    tty=True,
                    command=command,
                    stdin_open=True,
                    ports=self.ports,
                    **self.kwargs,
                )

            return str(self.container.id)

        except Exception as e:
            self.cleanup()
            raise RuntimeError(f"Failed to setup docker environment: {str(e)}")

    def execute(self, command: str | List[str]) -> tuple[int, str, str]:
        """Execute command in container.

        Args:
            command: Command to execute

        Returns:
            tuple: (exit_code, stdout, stderr)
        """
        if not self.container:
            raise RuntimeError("Container not initialized")

        if isinstance(command, list):
            command = " ".join(command)

        exit_code, output = self.container.exec_run(command, workdir=self.working_dir, demux=True)

        stdout = output[0].decode() if output[0] else ""
        stderr = output[1].decode() if output[1] else ""

        return exit_code, stdout, stderr

    def cleanup(self):
        """Stop and remove container."""
        if self.container:
            try:
                self.container.stop()
                self.container.remove()
            except DockerException:
                pass
            finally:
                self.container = None

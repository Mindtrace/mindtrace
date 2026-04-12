"""Client-side helper class for communicating with any ServerBase server."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from urllib.parse import urljoin
from uuid import UUID

import requests
from urllib3.util.url import Url, parse_url

from mindtrace.core import Mindtrace, Timeout, ifnone
from mindtrace.services.core.types import ServerStatus, ShutdownOutput, StatusOutput

if TYPE_CHECKING:
    from fastmcp import Client


class ConnectionManager(Mindtrace):
    """Client-side helper class for communicating with Mindtrace servers."""

    def __init__(self, url: Url | None = None, server_id: UUID | None = None, server_pid_file: str | None = None):
        super().__init__()
        self.url = ifnone(url, default=parse_url(self.config["MINDTRACE_DEFAULT_HOST_URLS"]["SERVICE"]))
        self._server_id = server_id
        self._server_pid_file = server_pid_file
        self._mcp_client: Client | None = None

    def shutdown(self, block: bool = True):
        """Shutdown the server.

        This method sends a shutdown request to the server. If block=True, it will also poll the server until it
        becomes unavailable, ensuring the shutdown process is complete.

        Args:
            block: If True, waits for the server to actually shut down. If False, returns immediately after sending
            the shutdown request.

        Example::

            from mindtrace.services import Service, ServerStatus

            cm = Service.launch()
            assert cm.status == ServerStatus.Available

            # Wait for shutdown to complete
            cm.shutdown(block=True)
            assert cm.status == ServerStatus.Down

            # Or send shutdown command and return immediately
            cm.shutdown(block=False)
        """
        # Send the shutdown request
        response = requests.request("POST", urljoin(str(self.url), "shutdown"), timeout=60)
        if response.status_code != 200:
            from fastapi import HTTPException

            raise HTTPException(response.status_code, response.content)

        # If not blocking, return immediately after sending the shutdown request
        if not block:
            return ShutdownOutput(shutdown=True)

        def check_server_down():
            """Check if server is down by trying to connect to status endpoint."""
            try:
                _ = requests.post(urljoin(str(self.url), "status"), timeout=2)
                # If we get any response, server is still up - raise exception to retry
                raise ConnectionError("Server still responding")
            except requests.exceptions.ConnectionError:
                # Connection failed - server is down, this is what we want
                return True
            except requests.exceptions.Timeout:
                # Timeout - server might be shutting down, this is what we want
                return True

        timeout_handler = Timeout(
            timeout=30,
            retry_delay=0.2,
            exceptions=(ConnectionError,),
            progress_bar=False,  # No progress bar for shutdown
        )
        try:
            timeout_handler.run(check_server_down)
        except TimeoutError:
            self.logger.error(f"Server at {self.url} did not shut down within timeout period.")
            raise TimeoutError(f"Server at {self.url} did not shut down within timeout period.")

        return ShutdownOutput(shutdown=True)

    async def ashutdown(self, block: bool = True):
        """Async shutdown of the server."""
        # Run the shutdown in a thread pool to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.shutdown, block)

    def status(self):
        """Get the status of the server.

        Returns ServerStatus.DOWN if the server is unreachable, otherwise returns the actual status.

        Returns:
            StatusOutput with the current server status.
        """
        try:
            response = requests.post(urljoin(str(self.url), "status"), timeout=10)
            if response.status_code != 200:
                return StatusOutput(status=ServerStatus.DOWN)

            result = response.json()
            return StatusOutput(**result)

        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout, requests.exceptions.RequestException):
            return StatusOutput(status=ServerStatus.DOWN)

    async def astatus(self):
        """Async get the status of the server.

        Returns ServerStatus.DOWN if the server is unreachable, otherwise returns the actual status.

        Returns:
            StatusOutput with the current server status.
        """
        import httpx

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(urljoin(str(self.url), "status"))

            if response.status_code != 200:
                return StatusOutput(status=ServerStatus.DOWN)

            result = response.json()
            return StatusOutput(**result)

        except (httpx.ConnectError, httpx.TimeoutException, httpx.RequestError):
            return StatusOutput(status=ServerStatus.DOWN)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.logger.debug(f"Shutting down {self.name} Server.")
        try:
            self.shutdown()
        except Exception:
            self.logger.exception("Shutdown failed during context manager exit")
        if exc_type is not None:
            self.logger.exception("Exception occurred", exc_info=(exc_type, exc_val, exc_tb))
        return False

    @property
    def mcp_url(self) -> str:
        """Return the MCP endpoint URL for this service instance using config paths."""
        from mindtrace.services.core.utils import build_mcp_url

        return build_mcp_url(
            self.url,
            self.config["MINDTRACE_MCP"]["MOUNT_PATH"],
            self.config["MINDTRACE_MCP"]["HTTP_APP_PATH"],
        )

    @property
    def mcp_client(self) -> Client:
        """Get an MCP client for this service.

        Returns a FastMCP Client instance that can be used to interact with the service
        through the MCP protocol. The client connects to the service's MCP endpoint.

        Returns:
            FastMCP Client instance for MCP protocol communication

        Example::
            cm = MyService.launch()
            client = cm.mcp_client
            # Use client for MCP protocol interactions
        """
        if self._mcp_client is None:
            from fastmcp import Client

            self._mcp_client = Client(self.mcp_url)
        return self._mcp_client

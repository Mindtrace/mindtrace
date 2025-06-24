"""Client-side helper class for communicating with any ServerBase server."""

import asyncio
import json
from typing import List
from urllib.parse import urljoin
from uuid import UUID

from fastapi import HTTPException
import requests
from urllib3.util.url import parse_url, Url

from mindtrace.core import Mindtrace, ifnone, Timeout
from mindtrace.services.base.types import Heartbeat, ServerStatus, ShutdownOutput



class ConnectionManager(Mindtrace):
    """Client-side helper class for communicating with Mindtrace servers."""

    def __init__(self, url: Url | None = None, server_id: UUID | None = None, server_pid_file: str | None = None):
        super().__init__()
        self.url = ifnone(url, default=parse_url(self.config["MINDTRACE_DEFAULT_HOST_URLS"]["Service"]))
        self._server_id = server_id
        self._server_pid_file = server_pid_file

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
            raise HTTPException(response.status_code, response.content)
        
        # If not blocking, return immediately after sending the shutdown request
        if not block:
            return ShutdownOutput(shutdown=True)
        
        def check_server_down():
            """Check if server is down by trying to connect to status endpoint."""
            try:
                test_response = requests.post(urljoin(str(self.url), "status"), timeout=2)
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
        from mindtrace.services.base.types import ServerStatus, StatusOutput
        
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
        from mindtrace.services.base.types import ServerStatus, StatusOutput
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
        finally:
            if exc_type is not None:
                info = (exc_type, exc_val, exc_tb)
                self.logger.exception("Exception occurred", exc_info=info)
                return self.suppress
        return False

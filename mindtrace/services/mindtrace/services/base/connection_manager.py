"""Client-side helper class for communicating with any ServerBase server."""

import json
from typing import List
from urllib.parse import urljoin
from uuid import UUID

from fastapi import HTTPException
import requests
from urllib3.util.url import parse_url, Url

from mindtrace.core import Mindtrace, ifnone
from mindtrace.services.base.types import Heartbeat, ServerStatus


class ConnectionManager(Mindtrace):
    """Client-side helper class for communicating with Mindtrace servers."""

    def __init__(self, url: Url | None = None, server_id: UUID | None = None, server_pid_file: str | None = None):
        super().__init__()
        self.url = ifnone(url, default=parse_url(self.config["MINDTRACE_DEFAULT_HOST_URLS"]["Service"]))
        self._server_id = server_id
        self._server_pid_file = server_pid_file

    @property
    def endpoints(self) -> List[str]:
        """Get the list of registered endpoints on the server."""
        response = requests.request("POST", urljoin(str(self.url), "endpoints"), timeout=60)
        if response.status_code != 200:
            raise HTTPException(response.status_code, response.content)
        return json.loads(response.content)["endpoints"]

    @property
    def status(self) -> ServerStatus:
        """Get the status of the server."""
        try:
            response = requests.post(urljoin(str(self.url), "status"), timeout=60)
            if response.status_code != 200:
                return ServerStatus.Down
            else:
                return ServerStatus(json.loads(response.content)["status"])
        except Exception as e:
            self.logger.warning(f"Failed to get status of server at {self.url}: {e}")
            return ServerStatus.Down

    def heartbeat(self) -> Heartbeat:
        """Get the heartbeat of the server.

        The heartbeat includes both the server's status, as well as any additional diagnostic information the server may
        provide.
        """
        response = requests.request("POST", urljoin(str(self.url), "heartbeat"), timeout=60)
        if response.status_code != 200:
            raise HTTPException(response.status_code, response.content)
        response = json.loads(response.content)["heartbeat"]
        return Heartbeat(
            status=ServerStatus(response["status"]),
            server_id=response["server_id"],
            message=response["message"],
            details=response["details"],
        )

    @property
    def server_id(self) -> UUID:
        """Get the server's unique id."""
        if self._server_id is not None:
            return self._server_id
        else:
            response = requests.post(urljoin(str(self.url), "server_id"), timeout=60)
            if response.status_code != 200:
                raise HTTPException(response.status_code, response.content)
            self._server_id = UUID(json.loads(response.content)["server_id"])
            return self._server_id

    @property
    def pid_file(self) -> str:
        """Get the server's pid file."""
        if self._server_pid_file is not None:
            return self._server_pid_file
        else:
            response = requests.post(urljoin(str(self.url), "pid_file"), timeout=60)
            if response.status_code != 200:
                raise HTTPException(response.status_code, response.content)
            return json.loads(response.content)["pid_file"]

    def shutdown(self):
        """Shutdown the server.

        Example::

            from mindtrace.services import Service, ServerStatus

            cm = Service.launch()
            assert cm.status == ServerStatus.Available

            cm.shutdown()
            assert cm.status == ServerStatus.Down
        """
        response = requests.request("POST", urljoin(str(self.url), "shutdown"), timeout=60)
        if response.status_code != 200:
            raise HTTPException(response.status_code, response.content)
        return response

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

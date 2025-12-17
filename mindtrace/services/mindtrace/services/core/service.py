"""Service base class. Provides unified methods for all Mindtrace (micro)services."""

import atexit
import json
import logging
import os
import re
import signal
import subprocess
import uuid
from contextlib import AsyncExitStack, asynccontextmanager
from importlib.metadata import version
from pathlib import Path
from typing import Any, Dict, Literal, Type, TypeVar, overload
from uuid import UUID

import fastapi
import psutil
import requests
from fastapi import FastAPI, HTTPException
from fastmcp import FastMCP
from urllib3.util.url import Url, parse_url

from mindtrace.core import Mindtrace, TaskSchema, Timeout, ifnone, ifnone_url, named_lambda
from mindtrace.core.logging.logger import track_operation
from mindtrace.services.core.connection_manager import ConnectionManager
from mindtrace.services.core.mcp_client_manager import MCPClientManager
from mindtrace.services.core.types import (
    EndpointsSchema,
    Heartbeat,
    HeartbeatSchema,
    PIDFileSchema,
    ServerIDSchema,
    ServerStatus,
    ShutdownSchema,
    StatusSchema,
)
from mindtrace.services.core.utils import generate_connection_manager

T = TypeVar("T", bound="Service")  # A generic variable that can be 'Service', or any subclass.
C = TypeVar("C", bound="ConnectionManager")  # '' '' '' 'ConnectionManager', or any subclass.


class Service(Mindtrace):
    """Base class for all Mindtrace services."""

    _status = ServerStatus.DOWN
    _client_interface: Type[C] | None = None
    _active_servers: dict[UUID, psutil.Process] = {}
    mcp: MCPClientManager = None

    def __init__(
        self,
        *,
        url: str | Url | None = None,
        host: str | None = None,
        port: int | None = None,
        summary: str | None = None,
        description: str | None = None,
        terms_of_service: str | None = None,
        license_info: Dict[str, str | Any] | None = None,
        live_service: bool = True,
        **kwargs,
    ):
        """Initialize server instance. This is for internal use by the launch() method.

        Args:
            url: Full URL string or Url object
            host: Host address (e.g. "localhost" or "192.168.1.100")
            port: Port number
            summary: Summary of the server
            description: Description of the server
            terms_of_service: Terms of service for the server
            license_info: License information for the server
            live_service: bool: set to True when launching via .launch(),
                set to False when querying endpoints in mindtrace.services.core.utils.py::generate_connection_manager
                Used to allow Service subclasses to have expensive __init__() methods without making .connect() slow

        Warning: Services should be created via the ServiceClass.launch() method. The __init__ method here should be
        considered private internal use.
        """
        super().__init__(**kwargs)
        self._status: ServerStatus = ServerStatus.AVAILABLE
        self._endpoints: dict[str, TaskSchema] = {}
        self.id, self.pid_file = self._generate_id_and_pid_file()

        # Build URL with the following priority:
        # 1. Explicit URL parameter
        # 2. Host/port parameters
        # 3. Default URL from config
        self._url = self.build_url(url=url, host=host, port=port)

        """
        self.logger = default_logger(
            name=self.unique_name,
            stream_level=logging.INFO,
            file_level=logging.DEBUG,
            file_name=self.default_log_file(),
        )
        """

        description = str(ifnone(description, default=f"{self.name} server."))
        version_str = "Mindtrace " + version("mindtrace-services")

        self.mcp = FastMCP(
            name=re.sub(r"server", "mcp server", description, flags=re.IGNORECASE),
            version=version_str,
        )
        # Configure MCP paths from config (defaults preserve current behavior)
        mcp_mount_path, mcp_http_app_path = self.get_mcp_paths()

        self.mcp_app = self.mcp.http_app(path=mcp_http_app_path)

        @asynccontextmanager
        async def combined_lifespan(app: FastAPI):
            """Combined lifespan for FastAPI and MCP app."""
            async with AsyncExitStack() as stack:
                # Enter MCP app lifespan
                await stack.enter_async_context(self.mcp_app.lifespan(app))
                # Service's own startup logic
                self.logger.info(f"Server {self.id} starting up.")
                yield
                await self.shutdown_cleanup()
                self.logger.info(f"Server {self.id} shut down.")

        self.app = FastAPI(
            title=self.name,
            description=description,
            summary=summary,
            version=version_str,
            terms_of_service=terms_of_service,
            license_info=license_info,
            lifespan=combined_lifespan,
        )
        # Mount MCP app at configured mount path
        self.app.mount(mcp_mount_path, self.mcp_app)

        self.add_endpoint(
            path="/endpoints",
            func=self.endpoints_func,
            schema=EndpointsSchema,
            as_tool=True,
        )
        self.add_endpoint(path="/status", func=self.status_func, schema=StatusSchema, as_tool=True)
        self.add_endpoint(
            path="/heartbeat",
            func=self.heartbeat_func,
            schema=HeartbeatSchema,
            as_tool=True,
        )
        self.add_endpoint(
            path="/server_id", func=named_lambda("server_id", lambda: {"server_id": self.id}), schema=ServerIDSchema
        )
        self.add_endpoint(
            path="/pid_file", func=named_lambda("pid_file", lambda: {"pid_file": self.pid_file}), schema=PIDFileSchema
        )
        self.add_endpoint(
            path="/shutdown", func=self.shutdown, schema=ShutdownSchema, autolog_kwargs={"log_level": logging.DEBUG}
        )

    def __init_subclass__(cls, **kwargs):
        """Set up MCP client manager for each service subclass."""
        super().__init_subclass__(**kwargs)
        cls.mcp = MCPClientManager(cls)

    def endpoints_func(self):
        """List all available endpoints for the service."""
        return {"endpoints": list(self._endpoints.keys())}

    def status_func(self):
        """Get the current status of the service."""
        return {"status": self.status.value}

    def heartbeat_func(self):
        """Perform a heartbeat check for the service."""
        return {"heartbeat": self.heartbeat()}

    @classmethod
    def _generate_id_and_pid_file(cls, unique_id: UUID | None = None, pid_file: str | None = None) -> tuple[UUID, str]:
        """Generate a unique_id and pid_file for the server.

        The logic used ensures that the pid_file contains the (human-readable) class name as well as the unique_id.
        """

        # The following logic assures that the pid_file contains the unique_id
        if unique_id is not None and pid_file is not None:
            if str(unique_id) not in pid_file:
                raise ValueError(f"unique_id {unique_id} not found in pid_file {pid_file}")
        elif unique_id is not None and pid_file is None:
            unique_id = unique_id
            pid_file = cls._server_id_to_pid_file(unique_id)
        elif unique_id is None and pid_file is not None:
            unique_id = cls._pid_file_to_server_id(pid_file)
            pid_file = pid_file
        else:  # unique_id is None and pid_file is None
            unique_id = uuid.uuid1()
            pid_file = cls._server_id_to_pid_file(unique_id)

        Path(pid_file).parent.mkdir(parents=True, exist_ok=True)
        return unique_id, pid_file

    @classmethod
    def _server_id_to_pid_file(cls, server_id: UUID) -> str:
        return os.path.join(cls.config["MINDTRACE_DIR_PATHS"]["SERVER_PIDS_DIR"], f"{cls.__name__}_{server_id}_pid.txt")

    @classmethod
    def _pid_file_to_server_id(cls, pid_file: str) -> UUID:
        return UUID(pid_file.split("_")[-2])

    @classmethod
    def status_at_host(cls, url: str | Url, timeout: int = 60) -> ServerStatus:
        """Check the status of the service at the given host url.

        This command may be used to check if a service (including this one) is available at a given host, useful for
        determining when a service has been successfully launched.

        Args:
            url: The host URL of the service.
        """
        url = parse_url(url) if isinstance(url, str) else url
        try:
            response = requests.request("POST", str(url) + "/status", timeout=timeout)
        except requests.exceptions.ConnectionError:
            return ServerStatus.DOWN
        if response.status_code != 200:
            return ServerStatus.DOWN

        status = ServerStatus(response.json()["status"])
        return status

    @classmethod
    def _connect_with_interrupt_handling(cls, url, process, timeout):
        """Connect while checking if the subprocess died."""
        if process.poll() is not None:
            if process.returncode == 0:
                raise SystemExit("Service exited cleanly.")
            elif process.returncode == -signal.SIGINT:
                raise KeyboardInterrupt("Service terminated by SIGINT.")
            else:
                raise RuntimeError(f"Server exited with code {process.returncode}")
        return cls.connect(url=url)

    @classmethod
    def connect(cls: Type[T], url: str | Url | None = None, timeout: int = 60) -> Any:
        """Connect to an existing service.

        The returned connection manager is determined by the registered connection manager for the service. If one has
        not explicitly been registered, the default connection manager (ConnectionManagerBase) will be used.

        Args:
            url: The host URL of the service.

        Returns:
            A connection manager for the service.

        Raises:
            HTTPException: If the server fails to connect, an HTTPException will be raised with status code 503.
        """
        url = ifnone_url(url, default=cls.default_url())
        host_status = cls.status_at_host(url, timeout=timeout)
        if host_status == ServerStatus.AVAILABLE:
            if cls._client_interface is None:
                return generate_connection_manager(cls)(url=url)
            else:
                return cls._client_interface(url=url)
        raise HTTPException(status_code=503, detail=f"Server failed to connect: {host_status}")

    @overload
    @classmethod
    def launch(
        cls: Type[T],
        *,
        url: str | Url | None = None,
        host: str | None = None,
        port: int | None = None,
        block: bool = False,
        num_workers: int = 1,
        wait_for_launch: Literal[False],
        timeout: int = 60,
        progress_bar: bool = True,
        **kwargs,
    ) -> None: ...

    @overload
    @classmethod
    def launch(
        cls: Type[T],
        *,
        url: str | Url | None = None,
        host: str | None = None,
        port: int | None = None,
        block: bool = False,
        num_workers: int = 1,
        wait_for_launch: Literal[True] | bool = True,
        timeout: int = 60,
        progress_bar: bool = True,
        **kwargs,
    ) -> Any: ...

    @classmethod
    def launch(
        cls: Type[T],
        *,
        url: str | Url | None = None,
        host: str | None = None,
        port: int | None = None,
        block: bool = False,
        num_workers: int = 1,
        wait_for_launch: bool = True,
        timeout: int = 60,
        progress_bar: bool = True,
        **kwargs,
    ):
        """Launch a new server instance.

        The server can be configured through either explicit URL parameters or through kwargs. All kwargs are passed
        directly to the server instance's __init__ method.

        Args:
            url: Full URL string or Url object (highest priority)
            host: Host address (used if url not provided)
            port: Port number (used if url not provided)
            block: If True, blocks the calling process and keeps the server running
            num_workers: Number of worker processes
            wait_for_launch: Whether to wait for server startup
            timeout: Timeout for server startup in seconds
            progress_bar: Show progress bar during startup
            **kwargs: Additional parameters passed to the server's __init__ method
        """
        # Build the launch URL with priority
        launch_url = cls.build_url(url=url, host=host, port=port)

        # Check that there is not already a service at the given URL
        try:
            existing_status = cls.status_at_host(launch_url)
            if existing_status != ServerStatus.DOWN:
                raise HTTPException(
                    status_code=400,
                    detail=f"Server {cls.unique_name} at {launch_url} is already running with status {existing_status}.",
                )
        except RuntimeError as e:
            cls.logger.warning(f"Another service is already running at {launch_url}. New service was NOT launched.")
            raise e

        # All kwargs (including URL params) go directly to init_params
        init_params = {"url": str(launch_url), **kwargs}

        # Create launch command
        server_id = uuid.uuid1()
        launch_command = [
            "python",
            "-m",
            "mindtrace.services.core.launcher",
            "-s",
            cls.unique_name,
            "-w",
            str(num_workers),
            "-b",
            f"{launch_url.host}:{launch_url.port}",
            "-p",
            cls._server_id_to_pid_file(server_id),
            "-k",
            "uvicorn.workers.UvicornWorker",
            "--init-params",
            json.dumps(init_params),
        ]
        cls.logger.warning(f'Launching {cls.unique_name} with command: "{launch_command}"')
        process = subprocess.Popen(launch_command)

        # Register cleanup if this is the first server
        cls._active_servers[server_id] = process
        if len(cls._active_servers) == 1:
            atexit.register(cls._cleanup_all_servers)
            try:
                signal.signal(signal.SIGTERM, lambda sig, frame: cls._cleanup_all_servers())
                signal.signal(signal.SIGINT, lambda sig, frame: cls._cleanup_all_servers())
            except ValueError:
                cls.logger.warning(
                    "Could not register signal handlers for server shutdown. This is normal if you launch a Service from another Service."
                )

        # Wait for server to be available and get connection manager
        connection_manager = None
        if wait_for_launch:
            timeout_handler = Timeout(
                timeout=timeout,
                exceptions=(ConnectionRefusedError, requests.exceptions.ConnectionError, HTTPException),
                progress_bar=progress_bar,
                desc=f"Launching {cls.unique_name.split('.')[-1]} at {launch_url}",
            )
            try:
                connection_manager = timeout_handler.run(
                    cls._connect_with_interrupt_handling, url=launch_url, process=process, timeout=timeout
                )
            except KeyboardInterrupt:
                cls.logger.warning("User interrupted the launch (Ctrl+C).")
                cls._cleanup_server(server_id)
                raise
            except SystemExit as e:
                cls.logger.info(str(e))
                cls._cleanup_server(server_id)
                raise
            except Exception as e:
                cls._cleanup_server(server_id)
                raise e

        # If blocking is requested, wait for the process
        if block:
            try:
                process.wait()
            except KeyboardInterrupt:
                cls._cleanup_server(server_id)
                raise
            finally:
                cls._cleanup_server(server_id)

        return connection_manager

    @property
    def endpoints(self) -> dict[str, TaskSchema]:
        """Return the available commands for the service."""
        return self._endpoints

    @property
    def status(self) -> ServerStatus:
        """Returns the current status of this service."""
        return self._status

    def heartbeat(self) -> Heartbeat:
        """Request the server to do a complete heartbeat check."""
        return Heartbeat(
            status=self.status,
            server_id=self.id,
            message="Heartbeat check successful.",
            details=None,
        )

    @classmethod
    def _cleanup_server(cls, server_id: UUID):
        if server_id in cls._active_servers:
            process = cls._active_servers[server_id]
            try:
                parent = psutil.Process(process.pid)
                children = parent.children(recursive=True)
                for child in children:
                    try:
                        child.terminate()
                    except psutil.NoSuchProcess:
                        pass
                try:
                    parent.terminate()
                    parent.wait(timeout=5)
                except psutil.NoSuchProcess:
                    pass
            except (psutil.NoSuchProcess, psutil.TimeoutExpired):
                cls.logger.debug("Process already terminated.")
            finally:
                del cls._active_servers[server_id]

    @classmethod
    def _cleanup_all_servers(cls):
        """Cleanup the servers."""
        for server_id in list(cls._active_servers.keys()):
            cls._cleanup_server(server_id)

    @staticmethod
    def shutdown() -> fastapi.Response:
        """HTTP endpoint to shut down the server."""
        os.kill(os.getppid(), signal.SIGTERM)  # kill the parent gunicorn process as it will respawn us otherwise
        os.kill(os.getpid(), signal.SIGTERM)  # kill ourselves as well
        return fastapi.Response(status_code=200, content="Server shutting down...")

    async def shutdown_cleanup(self):
        """Cleanup the server.

        Override this method in subclasses to shut down any additional resources (e.g. db connections) as necessary."""
        try:
            self.logger.debug(f"Successfully released resources for Server {self.id}.")
        except Exception as e:
            self.logger.warning(f"Server did not shut down properly: {e}")

    @classmethod
    def default_url(cls) -> Url:
        """Get the default URL for this server type from config.

        Priority:

        1. Server-specific URL from config
        2. Default ServerBase URL from config
        3. Fallback to localhost:8000
        """
        default_urls = cls.config["MINDTRACE_DEFAULT_HOST_URLS"]
        server_url = default_urls.get(cls.__name__.upper()) or default_urls.get("ServerBase", "http://localhost:8000")
        return parse_url(server_url)

    @classmethod
    def build_url(cls, url: str | Url | None = None, host: str | None = None, port: int | None = None) -> Url:
        """Build a URL with consistent priority logic.

        Priority:

        1. Explicit URL parameter
        2. Host/port parameters
        3. Default URL from config

        Args:
            url: Full URL string or Url object
            host: Host address (e.g. "localhost" or "192.168.1.100")
            port: Port number

        Returns:
            Parsed URL object
        """
        if url is not None:
            if isinstance(url, str):
                url = url + "/" if not url.endswith("/") else url
            return parse_url(url) if isinstance(url, str) else url

        if host is not None or port is not None:
            default_url = cls.default_url()
            final_host = host or default_url.host
            final_port = port or default_url.port
            return parse_url(f"http://{final_host}:{final_port}/")

        return cls.default_url()

    @classmethod
    def get_mcp_paths(cls) -> tuple[str, str]:
        """Return (mount_path, http_app_path) for MCP based on config defaults.

        Defaults:
        - mount_path: "/mcp-server"
        - http_app_path: "/mcp"
        """
        mcp_http_app_path = str(cls.config["MINDTRACE_MCP"]["HTTP_APP_PATH"])
        mcp_mount_path = str(cls.config["MINDTRACE_MCP"]["MOUNT_PATH"])
        if not mcp_http_app_path.startswith("/"):
            mcp_http_app_path = "/" + mcp_http_app_path
        if not mcp_mount_path.startswith("/"):
            mcp_mount_path = "/" + mcp_mount_path
        return mcp_mount_path, mcp_http_app_path

    @classmethod
    def register_connection_manager(cls, connection_manager: Type[ConnectionManager]):
        """Register a connection manager for this server."""
        cls._client_interface = connection_manager

    @classmethod
    def default_log_file(cls) -> str:
        """Get the default log file for this server type."""
        return os.path.join(cls.config["MINDTRACE_DIR_PATHS"]["LOGGER_DIR"], f"{cls.__name__}_logs.txt")

    def add_endpoint(
        self,
        path,
        func,
        schema: TaskSchema,
        api_route_kwargs=None,
        autolog_kwargs=None,
        methods: list[str] | None = None,
        scope: str = "public",
        as_tool: bool = False,
    ):
        """Register a new endpoint with optional role."""
        path = path.removeprefix("/")
        api_route_kwargs = ifnone(api_route_kwargs, default={})
        # Merge and override default autolog_kwargs
        default_autolog_kwargs = {
            "log_level": logging.INFO,
            "include_duration": True,
            "include_system_metrics": True,
            "system_metrics": ["cpu_percent", "memory_percent"],
        }
        autolog_kwargs = {**default_autolog_kwargs, **(autolog_kwargs or {})}
        self._endpoints[path] = schema
        if as_tool:
            self.add_tool(tool_name=path, func=func)
        wrapped = track_operation(
            name=func.__name__,
            service_name=self.name,
            logger=self.logger,
            log_level=autolog_kwargs.get("log_level", logging.INFO),
            include_system_metrics=autolog_kwargs.get("include_system_metrics", False),
            system_metrics=autolog_kwargs.get("system_metrics"),
        )(func)

        self.app.add_api_route(
            "/" + path,
            endpoint=wrapped,
            methods=ifnone(methods, default=["POST"]),
            **api_route_kwargs,
        )

    def add_tool(self, tool_name, func):
        """Add a tool to the MCP server, with an informative description including the tool and service name."""
        service_name = getattr(self, "name", self.__class__.__name__)
        # Use the function's docstring if available, otherwise log and use a default description
        if doc := func.__doc__:
            base_desc = doc.strip()
        else:
            base_desc = "No description provided."
            self.logger.warning(f"Function '{tool_name}' for service '{service_name}' has no docstring.")
        full_desc = f"{base_desc} \n This tool ('{tool_name}') belongs to the service '{service_name}'."
        self.mcp.tool(name=tool_name, description=full_desc)(func)

from typing import Any, Type

import httpx
from fastapi import HTTPException, Path, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from urllib3.util.url import Url

from mindtrace.core import ifnone_url
from mindtrace.services.core.connection_manager import ConnectionManager
from mindtrace.services.core.endpoint_spec import endpoint
from mindtrace.services.core.service import Service
from mindtrace.services.core.types import ServerStatus
from mindtrace.services.core.utils import generate_connection_manager
from mindtrace.services.gateway.proxy_connection_manager import ProxyConnectionManager
from mindtrace.services.gateway.types import AppConfig, RegisterAppTaskSchema


class GatewayConnectionManager(ConnectionManager):
    """Connection manager for Gateway services with app registration and proxy support."""

    def __init__(self, url: Url | None = None, **kwargs):
        super().__init__(url=url, **kwargs)
        self._registered_apps: dict[str, ProxyConnectionManager] = {}

    @property
    def registered_apps(self) -> list[str]:
        return list(self._registered_apps.keys())

    def register_app(self, name: str, url: str, connection_manager: ConnectionManager | None = None, **kwargs):
        """Register an app with the gateway, optionally creating a proxy for it."""
        res = httpx.post(
            str(self.url).rstrip("/") + "/register_app",
            json={"name": name, "url": url},
            timeout=60,
        )
        if res.status_code != 200:
            raise HTTPException(res.status_code, res.text)

        if connection_manager is not None:
            proxy_cm = ProxyConnectionManager(gateway_url=self.url, app_name=name, original_cm=connection_manager)
            self._registered_apps[name] = proxy_cm
            setattr(self, name, proxy_cm)

    async def aregister_app(self, name: str, url: str, connection_manager: ConnectionManager | None = None, **kwargs):
        """Async version of register_app."""
        async with httpx.AsyncClient(timeout=60) as client:
            res = await client.post(
                str(self.url).rstrip("/") + "/register_app",
                json={"name": name, "url": url},
            )
        if res.status_code != 200:
            raise HTTPException(res.status_code, res.text)

        if connection_manager is not None:
            proxy_cm = ProxyConnectionManager(gateway_url=self.url, app_name=name, original_cm=connection_manager)
            self._registered_apps[name] = proxy_cm
            setattr(self, name, proxy_cm)


class Gateway(Service):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.registered_routers = {}
        self.client = httpx.AsyncClient()

        # Enable CORS for the gateway
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @endpoint("register_app", schema=RegisterAppTaskSchema)
    def register_app(self, payload: AppConfig):
        """Register a FastAPI app with the gateway."""
        self.registered_routers[payload.name] = str(payload.url)

        async def forwarder(request: Request, path: str = Path(...)):
            return await self.forward_request(request, payload.name, path)

        self.app.add_api_route(
            f"/{payload.name}/{{path:path}}",
            forwarder,
            methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
        )

    async def forward_request(self, request: Request, app_name: str, path: str):
        """Forward the request to the registered app."""
        self.logger.debug(f"Forwarding request {request} to {app_name} at {path}.")
        if app_name not in self.registered_routers:
            raise HTTPException(status_code=404, detail=f"App '{app_name}' not found")

        app_url = self.registered_routers[app_name]
        if app_url.endswith("/"):
            url = f"{app_url}{path}"
        else:
            url = f"{app_url}/{path}"
        method = request.method
        headers = dict(request.headers)
        content = await request.body()

        try:
            response = await self.client.request(method, url, headers=headers, content=content)
            self.logger.debug(f"Returning response for {request} from {app_name} at {path}.")
            return JSONResponse(content=response.json(), status_code=response.status_code)
        except httpx.RequestError as e:
            self.logger.warning(f"Exception was raised on forwarded request {request} to {app_name} at {path}.")
            raise HTTPException(status_code=500, detail=str(e))

    @classmethod
    def connect(cls: Type["Gateway"], url: str | Url | None = None, timeout: int = 60) -> Any:
        """Connect to an existing Gateway service.

        Returns a GatewayConnectionManager that inherits both the dynamically
        generated endpoint methods (heartbeat, endpoints, etc.) and the
        enhanced register_app/aregister_app with proxy support.
        """
        url = ifnone_url(url, default=cls.default_url())
        host_status = cls.status_at_host(url, timeout=timeout)

        if host_status == ServerStatus.AVAILABLE:
            # Generate a CM class with dynamic methods for all gateway endpoints
            base_cm_cls = generate_connection_manager(cls)

            # Create a combined class: GatewayConnectionManager's register_app/aregister_app
            # take precedence (MRO) over the dynamically generated versions
            combined_cls = type(
                "GatewayConnectionManager",
                (GatewayConnectionManager, base_cm_cls),
                {},
            )
            return combined_cls(url=url)

        raise HTTPException(status_code=503, detail=f"Server failed to connect: {host_status}")

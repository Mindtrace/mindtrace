from typing import Any, Type

import httpx
from fastapi import HTTPException, Path, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from urllib3.util.url import Url

from mindtrace.core import ifnone_url
from mindtrace.services.core.connection_manager import ConnectionManager
from mindtrace.services.core.service import Service
from mindtrace.services.core.types import ServerStatus
from mindtrace.services.core.utils import generate_connection_manager
from mindtrace.services.gateway.proxy_connection_manager import ProxyConnectionManager
from mindtrace.services.gateway.types import AppConfig, RegisterAppTaskSchema


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

        self.add_endpoint("/register_app", func=self.register_app, schema=RegisterAppTaskSchema, methods=["POST"])

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
        # Ensure proper URL construction with correct path separator
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
        """Connect to an existing Gateway service with enhanced connection manager."""
        url = ifnone_url(url, default=cls.default_url())
        host_status = cls.status_at_host(url, timeout=timeout)

        if host_status == ServerStatus.AVAILABLE:
            # Generate the base connection manager constructor for this specific Gateway class
            base_cm_constructor = generate_connection_manager(cls)

            # Create the base connection manager instance
            base_cm = base_cm_constructor(url=url)

            # Add enhanced functionality to the instance
            base_cm._registered_apps = {}

            # Store original methods if they exist
            original_register_app = getattr(base_cm, "register_app", None)
            original_aregister_app = getattr(base_cm, "aregister_app", None)

            def enhanced_register_app(
                name: str, url: str, connection_manager: ConnectionManager | None = None, **kwargs
            ):
                """Enhanced register_app that also sets up proxy functionality."""
                # Call the original method to register with Gateway
                result = original_register_app(name=name, url=url, **kwargs) if original_register_app else None

                if connection_manager:
                    # Create proxy and attach as attribute
                    proxy_cm = ProxyConnectionManager(
                        gateway_url=base_cm.url, app_name=name, original_cm=connection_manager
                    )
                    base_cm._registered_apps[name] = proxy_cm
                    setattr(base_cm, name, proxy_cm)

                return result

            async def enhanced_aregister_app(
                name: str, url: str, connection_manager: ConnectionManager | None = None, **kwargs
            ):
                """Async version of enhanced register_app."""
                # Call the original async method
                result = await original_aregister_app(name=name, url=url, **kwargs) if original_aregister_app else None

                if connection_manager:
                    # Create proxy and attach as attribute
                    proxy_cm = ProxyConnectionManager(
                        gateway_url=base_cm.url, app_name=name, original_cm=connection_manager
                    )
                    base_cm._registered_apps[name] = proxy_cm
                    setattr(base_cm, name, proxy_cm)

                return result

            # Add enhanced methods to the instance
            base_cm.register_app = enhanced_register_app
            base_cm.aregister_app = enhanced_aregister_app

            # Add registered_apps as a dynamic property
            def get_registered_apps(self):
                return list(self._registered_apps.keys())

            # Create a property descriptor and bind it to the instance
            base_cm.__class__.registered_apps = property(get_registered_apps)

            return base_cm

        raise HTTPException(status_code=503, detail=f"Server failed to connect: {host_status}")

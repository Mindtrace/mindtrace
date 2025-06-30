from typing import Type

import httpx
from fastapi import HTTPException, Request, Path
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from urllib3.util.url import Url

from mindtrace.core import ifnone_url, TaskSchema
from mindtrace.services import (
    AppConfig, 
    ConnectionManager, 
    generate_connection_manager, 
    ProxyConnectionManager, 
    RegisterAppTaskSchema, 
    ServerStatus, 
    Service
)


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

        self.add_endpoint("/register_app", func=self.register_app, schema=RegisterAppTaskSchema(), methods=["POST"])

    def register_app(self, payload: AppConfig):
        """Register a FastAPI app with the gateway."""
        self.registered_routers[payload.name] = payload.url

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
        url = f"{app_url}{path}"
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
    def connect(cls: Type["Gateway"], url: str | Url | None = None, timeout: int = 60):
        """Connect to an existing Gateway service with enhanced connection manager."""
        url = ifnone_url(url, default=cls.default_url())
        host_status = cls.status_at_host(url, timeout=timeout)
        
        if host_status == ServerStatus.AVAILABLE:
            # Generate the base connection manager for this specific Gateway class
            base_cm_class = generate_connection_manager(cls)
            
            # Create enhanced version with proxy functionality
            class EnhancedGatewayConnectionManager(base_cm_class):
                def __init__(self, *args, **kwargs):
                    super().__init__(*args, **kwargs)
                    self._registered_apps = {}
                
                @property 
                def registered_apps(self):
                    return list(self._registered_apps.keys())
                
                def register_app(self, name: str, url: str, connection_manager: ConnectionManager | None = None, **kwargs):
                    """Enhanced register_app that also sets up proxy functionality.
                    
                    Args:
                        name: The name of the app to register
                        url: The URL of the app to register  
                        connection_manager: Optional connection manager for the registered app
                        **kwargs: Additional arguments passed to the Gateway's register_app method
                    
                    Returns:
                        The result from the Gateway's register_app endpoint
                    """
                    # Call the parent (auto-generated) method to register with Gateway
                    result = super().register_app(name=name, url=url, **kwargs)
                    
                    if connection_manager:
                        # Create proxy and attach as attribute
                        proxy_cm = ProxyConnectionManager(
                            gateway_url=self.url,
                            app_name=name, 
                            original_cm=connection_manager
                        )
                        self._registered_apps[name] = proxy_cm
                        setattr(self, name, proxy_cm)
                    
                    return result
                
                async def aregister_app(self, name: str, url: str, connection_manager: ConnectionManager | None = None, **kwargs):
                    """Async version of enhanced register_app."""
                    # Call the parent (auto-generated) async method
                    result = await super().aregister_app(name=name, url=url, **kwargs)
                    
                    if connection_manager:
                        # Create proxy and attach as attribute
                        proxy_cm = ProxyConnectionManager(
                            gateway_url=self.url,
                            app_name=name, 
                            original_cm=connection_manager
                        )
                        self._registered_apps[name] = proxy_cm
                        setattr(self, name, proxy_cm)
                    
                    return result
            
            # Set a proper class name for debugging
            EnhancedGatewayConnectionManager.__name__ = f"{cls.__name__}ConnectionManager"
            
            return EnhancedGatewayConnectionManager(url=url)
        
        raise HTTPException(status_code=503, detail=f"Server failed to connect: {host_status}")
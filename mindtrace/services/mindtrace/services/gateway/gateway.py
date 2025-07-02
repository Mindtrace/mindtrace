from typing import Type, List, Dict, Any

from fastapi import HTTPException, Request, Path
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import httpx
from urllib3.util.url import Url
from pydantic import BaseModel

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


class AppInfo(BaseModel):
    """Information about a registered app."""
    name: str
    url: str
    endpoints: Dict[str, Dict[str, Any]]  # endpoint_name -> {input_schema, output_schema, ...}


class ListAppsResponse(BaseModel):
    """Response model for list_apps endpoint."""
    apps: List[str]


class ListAppsWithSchemasResponse(BaseModel):
    """Enhanced response model for list_apps_with_schemas endpoint."""
    apps: List[AppInfo]


class ListAppsTaskSchema(TaskSchema):
    """Schema for listing registered apps."""
    name: str = "list_apps"
    output_schema: BaseModel = ListAppsResponse


class ListAppsWithSchemasTaskSchema(TaskSchema):
    """Schema for listing registered apps with their endpoints and schemas."""
    name: str = "list_apps_with_schemas"
    output_schema: BaseModel = ListAppsWithSchemasResponse


class Gateway(Service):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.registered_routers = {}
        self.registered_app_info = {}  # Used for apps that provide schemas (i.e. mindtrace-derived apps)
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
        self.add_endpoint("/list_apps", func=self.list_apps, schema=ListAppsTaskSchema(), methods=["POST"])
        self.add_endpoint("/list_apps_with_schemas", func=self.list_apps_with_schemas, schema=ListAppsWithSchemasTaskSchema(), methods=["POST"])

    def register_app(self, payload: AppConfig):
        """Register a FastAPI app with the gateway."""
        self.registered_routers[payload.name] = str(payload.url)
        
        # Try to fetch endpoint information from the registered service
        try:
            endpoints_info = self._fetch_service_endpoints(str(payload.url))
            self.registered_app_info[payload.name] = {
                "name": payload.name,
                "url": str(payload.url),
                "endpoints": endpoints_info
            }
        except Exception as e:
            # If we can't fetch endpoints, store basic info
            self.logger.warning(f"Could not fetch endpoints for {payload.name}: {e}")
            self.registered_app_info[payload.name] = {
                "name": payload.name,
                "url": str(payload.url),
                "endpoints": {}
            }

        async def forwarder(request: Request, path: str = Path(...)):
            return await self.forward_request(request, payload.name, path)

        self.app.add_api_route(
            f"/{payload.name}/{{path:path}}",
            forwarder,
            methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
        )

    def _fetch_service_endpoints(self, service_url: str) -> Dict[str, Dict[str, Any]]:
        """Fetch endpoint information from a registered service."""
        import requests
        
        try:
            # Try to get endpoints from the service
            response = requests.post(f"{service_url.rstrip('/')}/endpoints", timeout=10)
            if response.status_code == 200:
                endpoints_data = response.json()
                endpoints_list = endpoints_data.get("endpoints", [])
                
                # Try to get detailed schema information from the service
                # First, try the new detailed_endpoints endpoint if it exists
                try:
                    schema_response = requests.post(f"{service_url.rstrip('/')}/detailed_endpoints", timeout=10)
                    if schema_response.status_code == 200:
                        detailed_endpoints = schema_response.json().get("endpoints", {})
                        
                        # Build endpoints info with schema details
                        endpoints_info = {}
                        for endpoint_name in endpoints_list:
                            # Skip system endpoints for cleaner output
                            if endpoint_name in ["status", "heartbeat", "endpoints", "detailed_endpoints", "server_id", "pid_file", "shutdown"]:
                                continue
                            
                            if endpoint_name in detailed_endpoints:
                                endpoint_detail = detailed_endpoints[endpoint_name]
                                endpoints_info[endpoint_name] = {
                                    "name": endpoint_name,
                                    "path": f"/{endpoint_name}",
                                    "methods": ["POST"],  # Default assumption
                                    "input_schema": endpoint_detail.get("input_schema"),
                                    "output_schema": endpoint_detail.get("output_schema")
                                }
                            else:
                                # Fallback for endpoints without detailed info
                                endpoints_info[endpoint_name] = {
                                    "name": endpoint_name,
                                    "path": f"/{endpoint_name}",
                                    "methods": ["POST"],
                                    "input_schema": None,
                                    "output_schema": None
                                }
                        
                        return endpoints_info
                except Exception:
                    # Fall back to basic endpoint info if detailed_endpoints fails
                    pass
                
                # Fallback: basic endpoint information without schemas
                endpoints_info = {}
                for endpoint_name in endpoints_list:
                    # Skip system endpoints for cleaner output
                    if endpoint_name in ["status", "heartbeat", "endpoints", "detailed_endpoints", "server_id", "pid_file", "shutdown"]:
                        continue
                    
                    endpoints_info[endpoint_name] = {
                        "name": endpoint_name,
                        "path": f"/{endpoint_name}",
                        "methods": ["POST"],  # Default assumption
                        "input_schema": None,
                        "output_schema": None
                    }
                
                return endpoints_info
        except Exception as e:
            self.logger.debug(f"Failed to fetch endpoints from {service_url}: {e}")
        
        return {}

    def list_apps(self) -> Dict[str, List[str]]:
        """Return list of currently registered apps."""
        return {"apps": list(self.registered_routers.keys())}

    def list_apps_with_schemas(self) -> Dict[str, List[AppInfo]]:
        """Return detailed information about registered apps including their endpoints and schemas."""
        apps_info = []
        for app_name, app_info in self.registered_app_info.items():
            apps_info.append(AppInfo(**app_info))
        
        return {"apps": apps_info}

    async def forward_request(self, request: Request, app_name: str, path: str):
        """Forward the request to the registered app."""
        self.logger.debug(f"Forwarding request {request} to {app_name} at {path}.")
        if app_name not in self.registered_routers:
            raise HTTPException(status_code=404, detail=f"App '{app_name}' not found")

        app_url = self.registered_routers[app_name]
        # Ensure proper URL construction with correct path separator
        if app_url.endswith('/'):
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
    def connect(cls: Type["Gateway"], url: str | Url | None = None, timeout: int = 60):
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
            
            # Sync with existing apps on the Gateway
            try:
                existing_apps_response = base_cm.list_apps()
                # Handle both dict and Pydantic model responses
                if hasattr(existing_apps_response, 'apps'):
                    existing_apps = existing_apps_response.apps
                else:
                    existing_apps = existing_apps_response.get("apps", [])
                for app_name in existing_apps:
                    # Create placeholder entries for existing apps (without connection managers)
                    base_cm._registered_apps[app_name] = None
            except Exception as e:
                # If syncing fails, continue with empty registry
                pass
            
            # Store original methods if they exist
            original_register_app = getattr(base_cm, 'register_app', None)
            original_aregister_app = getattr(base_cm, 'aregister_app', None)
            
            def enhanced_register_app(name: str, url: str, connection_manager: ConnectionManager | None = None, **kwargs):
                """Enhanced register_app that also sets up proxy functionality."""
                # Call the original method to register with Gateway
                result = original_register_app(name=name, url=url, **kwargs) if original_register_app else None
                
                if connection_manager:
                    # Create proxy and attach as attribute
                    proxy_cm = ProxyConnectionManager(
                        gateway_url=base_cm.url,
                        app_name=name, 
                        original_cm=connection_manager
                    )
                    base_cm._registered_apps[name] = proxy_cm
                    setattr(base_cm, name, proxy_cm)
                else:
                    # Register without proxy (basic registration)
                    base_cm._registered_apps[name] = None
                
                return result
            
            async def enhanced_aregister_app(name: str, url: str, connection_manager: ConnectionManager | None = None, **kwargs):
                """Async version of enhanced register_app."""
                # Call the original async method
                result = await original_aregister_app(name=name, url=url, **kwargs) if original_aregister_app else None
                
                if connection_manager:
                    # Create proxy and attach as attribute
                    proxy_cm = ProxyConnectionManager(
                        gateway_url=base_cm.url,
                        app_name=name, 
                        original_cm=connection_manager
                    )
                    base_cm._registered_apps[name] = proxy_cm
                    setattr(base_cm, name, proxy_cm)
                else:
                    # Register without proxy (basic registration)
                    base_cm._registered_apps[name] = None
                
                return result
            
            def enhanced_registered_apps():
                """Enhanced registered_apps method that returns detailed app information with schemas."""
                try:
                    # Call the new list_apps_with_schemas endpoint
                    response = base_cm.list_apps_with_schemas()
                    if hasattr(response, 'apps'):
                        return response.apps
                    else:
                        return response.get("apps", [])
                except Exception as e:
                    # Fallback to basic list if enhanced endpoint fails
                    try:
                        basic_response = base_cm.list_apps()
                        if hasattr(basic_response, 'apps'):
                            return basic_response.apps
                        else:
                            return basic_response.get("apps", [])
                    except Exception:
                        return list(base_cm._registered_apps.keys())
            
            # Add enhanced methods to the instance
            base_cm.register_app = enhanced_register_app
            base_cm.aregister_app = enhanced_aregister_app
            base_cm.registered_apps = enhanced_registered_apps
            
            return base_cm
        
        raise HTTPException(status_code=503, detail=f"Server failed to connect: {host_status}")
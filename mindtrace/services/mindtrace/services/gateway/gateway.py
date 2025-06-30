from fastapi import HTTPException, Request, Path
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import httpx

from mindtrace.core import TaskSchema
from mindtrace.services import AppConfig, RegisterAppTaskSchema, Service


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
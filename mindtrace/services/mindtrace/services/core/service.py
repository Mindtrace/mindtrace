from typing import Dict, Type

from fastapi import HTTPException
from mtrix import MtrixBase
from mtrix.services import ConnectionManagerBase, ServerBase
from pydantic import BaseModel
import httpx

# Simple inline utility to avoid import issues
def ifnone(val, default):
    """Return the given value if it is not None, else return the default."""
    return val if val is not None else default


class TaskSchema(BaseModel):
    """A task schema with strongly-typed input and output models"""
    name: str
    input_schema: Type[BaseModel]
    output_schema: Type[BaseModel]


def generate_connection_manager(service_cls):
    """Generates a dedicated ConnectionManager class with one method per endpoint."""

    class_name = f"{service_cls.__name__}ConnectionManager"

    class ServiceConnectionManager(ConnectionManagerBase):
        pass  # Methods will be added dynamically

    # Dynamically define one method per endpoint
    for task_name, task in service_cls().tasks.items():
        task_path = f"/{task_name}"

        def make_method(task_path, input_schema, output_schema):
            def method(self, blocking: bool = True, **kwargs):
                payload = input_schema(**kwargs).dict()
                res = httpx.post(
                    str(self.url).rstrip('/') + task_path,
                    json=payload,
                    params={"blocking": str(blocking).lower()},
                    timeout=30
                )
                if res.status_code != 200:
                    raise HTTPException(res.status_code, res.text)
                result = res.json()
                if not blocking:
                    return result  # raw job result dict
                return output_schema(**result)
            
            async def amethod(self, blocking: bool = True, **kwargs):
                payload = input_schema(**kwargs).dict()
                async with httpx.AsyncClient(timeout=30) as client:
                    res = await client.post(
                        str(self.url).rstrip('/') + task_path,
                        json=payload,
                        params={"blocking": str(blocking).lower()}
                    )
                if res.status_code != 200:
                    raise HTTPException(res.status_code, res.text)
                result = res.json()
                if not blocking:
                    return result  # raw job result dict
                return output_schema(**result)
            
            return method, amethod

        method, amethod = make_method(task_path, task.input_schema, task.output_schema)
        
        # Set up sync method
        method.__name__ = task_name
        method.__doc__ = f"Calls the `{task_name}` pipeline at `{task_path}`"
        setattr(ServiceConnectionManager, task_name, method)
        
        # Set up async method
        amethod.__name__ = f"a{task_name}"
        amethod.__doc__ = f"Async version: Calls the `{task_name}` pipeline at `{task_path}`"
        setattr(ServiceConnectionManager, f"a{task_name}", amethod)

    def get_job(self, job_id: str):
        res = httpx.get(str(self.url).rstrip('/') + f"/job/{job_id}", timeout=10)
        if res.status_code == 404:
            return None
        elif res.status_code != 200:
            raise HTTPException(res.status_code, res.text)
        return res.json()
    
    async def aget_job(self, job_id: str):
        async with httpx.AsyncClient(timeout=10) as client:
            res = await client.get(str(self.url).rstrip('/') + f"/job/{job_id}")
        if res.status_code == 404:
            return None
        elif res.status_code != 200:
            raise HTTPException(res.status_code, res.text)
        return res.json()
    
    setattr(ServiceConnectionManager, "get_job", get_job)
    setattr(ServiceConnectionManager, "aget_job", aget_job)

    ServiceConnectionManager.__name__ = class_name
    return ServiceConnectionManager


class Service(ServerBase):
    _tasks: Dict[str, TaskSchema] = {}
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @property
    def tasks(self) -> Dict[str, TaskSchema]:
        return self._tasks

    def add_endpoint(
        self,
        path,
        func,
        task: TaskSchema = None,
        api_route_kwargs=None,
        autolog_kwargs=None,
        methods: list[str] | None = None,
        scope: str = "public",
    ):
        """Register a new endpoint with optional role."""
        path = path.removeprefix("/")
        api_route_kwargs = ifnone(api_route_kwargs, default={})
        autolog_kwargs = ifnone(autolog_kwargs, default={})
        self._endpoints.append(path)
        self._endpoints_metadata[path] = {"methods": ifnone(methods, default=["POST"]), "role": scope}
        self.app.add_api_route(
            "/" + path,
            endpoint=MtrixBase.autolog(self=self, **autolog_kwargs)(func),
            methods=ifnone(methods, default=["POST"]),
            **api_route_kwargs,
        )
        if task is not None:
            self._tasks[task.name] = task
        else:
            self.logger.warning(f"No task provided for endpoint {path}. This behavior will be deprecated in the future.")


    @classmethod
    def connect(cls, url: str, **kwargs) -> ConnectionManagerBase:
        """Connect to a running instance of this Tool.

        If no custom ConnectionManager is registered, one will be auto-generated based on the Tool's pipelines.
        """
        if cls._client_interface is ConnectionManagerBase:
            cls._client_interface = generate_connection_manager(cls)
        return super().connect(url=url, **kwargs)

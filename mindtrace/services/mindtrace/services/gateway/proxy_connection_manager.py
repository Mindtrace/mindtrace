from typing import Any, Dict

import httpx
from fastapi import HTTPException
from urllib3.util.url import Url

from mindtrace.services.core.connection_manager import ConnectionManager


class ProxyConnectionManager:
    """A schema-aware proxy that forwards requests through the gateway instead of directly to the service."""

    def __init__(self, gateway_url: str | Url, app_name: str, original_cm: ConnectionManager):
        """Initializes the ProxyConnectionManager.

        Args:
            gateway_url: The base URL of the gateway.
            app_name: The registered app name.
            original_cm: The original connection manager (must have been created via generate_connection_manager).
        """
        self.gateway_url = str(gateway_url).rstrip("/")
        self.app_name = app_name
        self.original_cm = original_cm

        self._service_endpoints = self._extract_service_endpoints(original_cm)
        self._generate_proxy_methods()

    @staticmethod
    def _extract_service_endpoints(original_cm: ConnectionManager) -> Dict[str, Any]:
        """Extract service endpoints from the original connection manager.

        Connection managers created by ``generate_connection_manager`` store
        ``_service_class`` and ``_service_endpoints`` on the generated class.
        These attributes may also be set directly on the instance.
        """
        # Check class first (generate_connection_manager sets these on the class)
        cm_cls = original_cm.__class__
        if hasattr(cm_cls, "_service_endpoints"):
            return cm_cls._service_endpoints
        if hasattr(cm_cls, "_service_class"):
            class_endpoints = getattr(cm_cls._service_class, "__endpoints__", {})
            return {path: spec.schema for path, spec in class_endpoints.items()}

        # Check instance (e.g. for manually configured CMs)
        if hasattr(original_cm, "_service_endpoints"):
            return original_cm._service_endpoints
        if hasattr(original_cm, "_service_class"):
            class_endpoints = getattr(original_cm._service_class, "__endpoints__", {})
            return {path: spec.schema for path, spec in class_endpoints.items()}

        raise ValueError(
            f"Cannot extract endpoints from {cm_cls.__name__}. "
            "The connection manager must be created via generate_connection_manager()."
        )

    def _generate_proxy_methods(self):
        """Generate proxy methods for each service endpoint."""
        for endpoint_name, endpoint_schema in self._service_endpoints.items():
            sync_method = self._create_proxy_method(endpoint_name, endpoint_schema, is_async=False)
            setattr(self, endpoint_name, sync_method)

            async_method = self._create_proxy_method(endpoint_name, endpoint_schema, is_async=True)
            setattr(self, f"a{endpoint_name}", async_method)

    def _create_proxy_method(self, endpoint_name: str, endpoint_schema: Any, is_async: bool):
        """Create a proxy method that routes to the gateway."""
        endpoint_url = f"{self.gateway_url}/{self.app_name}/{endpoint_name}"

        if is_async:

            async def async_proxy_method(**kwargs):
                if hasattr(endpoint_schema, "input_schema") and endpoint_schema.input_schema is not None:
                    try:
                        payload = endpoint_schema.input_schema(**kwargs).model_dump()
                    except Exception:
                        payload = kwargs
                else:
                    payload = kwargs

                async with httpx.AsyncClient(timeout=60) as client:
                    response = await client.post(endpoint_url, json=payload)

                if response.status_code != 200:
                    raise HTTPException(response.status_code, response.text)

                try:
                    result = response.json()
                except Exception:
                    result = {"success": True}

                if hasattr(endpoint_schema, "output_schema") and endpoint_schema.output_schema is not None:
                    try:
                        return endpoint_schema.output_schema(**result)
                    except Exception:
                        return result
                return result

            async_proxy_method.__name__ = f"a{endpoint_name}"
            async_proxy_method.__doc__ = f"Async proxy for {endpoint_name} endpoint via gateway"
            return async_proxy_method

        else:

            def sync_proxy_method(**kwargs):
                if hasattr(endpoint_schema, "input_schema") and endpoint_schema.input_schema is not None:
                    try:
                        payload = endpoint_schema.input_schema(**kwargs).model_dump()
                    except Exception:
                        payload = kwargs
                else:
                    payload = kwargs

                response = httpx.post(endpoint_url, json=payload, timeout=60)

                if response.status_code != 200:
                    raise HTTPException(response.status_code, response.text)

                try:
                    result = response.json()
                except Exception:
                    result = {"success": True}

                if hasattr(endpoint_schema, "output_schema") and endpoint_schema.output_schema is not None:
                    try:
                        return endpoint_schema.output_schema(**result)
                    except Exception:
                        return result
                return result

            sync_proxy_method.__name__ = endpoint_name
            sync_proxy_method.__doc__ = f"Sync proxy for {endpoint_name} endpoint via gateway"
            return sync_proxy_method

    def __getattr__(self, attr_name):
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{attr_name}'")

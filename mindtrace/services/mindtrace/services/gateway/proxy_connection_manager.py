from typing import Any, Dict

import httpx
import requests
from urllib3.util.url import Url

from mindtrace.services.core.connection_manager import ConnectionManager


class ProxyConnectionManager:
    """A schema-aware proxy that forwards requests through the gateway instead of directly through the wrapped connection manager."""

    def __init__(self, gateway_url: str | Url, app_name: str, original_cm: ConnectionManager):
        """Initializes the ProxyConnectionManager.

        Args:
            gateway_url: The base URL of the gateway.
            app_name: The registered app name.
            original_cm: The original connection manager.
        """
        object.__setattr__(self, "gateway_url", str(gateway_url).rstrip("/"))  # Ensure no trailing slash
        object.__setattr__(self, "app_name", app_name)
        object.__setattr__(self, "original_cm", original_cm)

        # Extract service endpoints from the original connection manager
        # Connection managers store the service class they were generated from
        self._service_endpoints = self._extract_service_endpoints(original_cm)

        # Generate proxy methods for each service endpoint
        self._generate_proxy_methods()

    def _extract_service_endpoints(self, original_cm: ConnectionManager) -> Dict[str, Any]:
        """Extract service endpoints from the original connection manager.

        This attempts to get the service endpoints that were used to generate
        the original connection manager.
        """
        # Try to access the service endpoints through the connection manager
        # The connection manager should have been created from a service with _endpoints
        if hasattr(original_cm.__class__, "_service_class"):
            # If the CM class stores the service class, get endpoints from there
            service_cls = original_cm.__class__._service_class
            temp_service = service_cls()
            return temp_service._endpoints
        elif hasattr(original_cm.__class__, "_service_endpoints"):
            # If the CM class stores the endpoints directly
            return original_cm.__class__._service_endpoints
        elif hasattr(original_cm, "_service_class"):
            # If the CM instance stores the service class, get endpoints from there
            service_cls = original_cm._service_class
            temp_service = service_cls()
            return temp_service._endpoints
        elif hasattr(original_cm, "_service_endpoints"):
            # If the CM instance stores the endpoints directly
            return original_cm._service_endpoints
        else:
            # Fallback: try to infer endpoints from the connection manager methods
            # This is less reliable but better than nothing
            return self._infer_endpoints_from_methods(original_cm)

    def _infer_endpoints_from_methods(self, original_cm: ConnectionManager) -> Dict[str, Any]:
        """Fallback method to infer service endpoints from connection manager methods."""
        endpoints = {}

        # Get all methods from the connection manager that look like service endpoints
        protected_methods = ["shutdown", "ashutdown", "status", "astatus", "url", "endpoints"]

        for attr_name in dir(original_cm):
            if (
                not attr_name.startswith("_")
                and attr_name not in protected_methods
                and callable(getattr(original_cm, attr_name))
            ):
                # Create a minimal endpoint schema for this method
                # This won't have proper input/output validation but will work for routing
                endpoints[attr_name] = type(
                    "MockTaskSchema", (), {"input_schema": None, "output_schema": None, "name": attr_name}
                )()

        return endpoints

    def _generate_proxy_methods(self):
        """Generate proxy methods for each service endpoint."""
        for endpoint_name, endpoint_schema in self._service_endpoints.items():
            # Create sync method
            sync_method = self._create_proxy_method(endpoint_name, endpoint_schema, is_async=False)
            setattr(self, endpoint_name, sync_method)

            # Create async method
            async_method = self._create_proxy_method(endpoint_name, endpoint_schema, is_async=True)
            setattr(self, f"a{endpoint_name}", async_method)

    def _create_proxy_method(self, endpoint_name: str, endpoint_schema: Any, is_async: bool):
        """Create a proxy method that routes to the gateway."""
        endpoint_url = f"{self.gateway_url}/{self.app_name}/{endpoint_name}"

        if is_async:

            async def async_proxy_method(**kwargs):
                # Validate input if schema is available
                if hasattr(endpoint_schema, "input_schema") and endpoint_schema.input_schema is not None:
                    try:
                        payload = endpoint_schema.input_schema(**kwargs).model_dump()
                    except Exception:
                        # Fallback to raw kwargs if validation fails
                        payload = kwargs
                else:
                    payload = kwargs

                # Make async HTTP request
                async with httpx.AsyncClient(timeout=60) as client:
                    response = await client.post(endpoint_url, json=payload)

                if response.status_code != 200:
                    raise RuntimeError(f"Gateway proxy request failed: {response.text}")

                # Parse response
                try:
                    result = response.json()
                except Exception:
                    result = {"success": True}  # Default for empty responses

                # Validate output if schema is available
                if hasattr(endpoint_schema, "output_schema") and endpoint_schema.output_schema is not None:
                    try:
                        return endpoint_schema.output_schema(**result)
                    except Exception:
                        # Fallback to raw result if validation fails
                        return result
                else:
                    return result

            async_proxy_method.__name__ = f"a{endpoint_name}"
            async_proxy_method.__doc__ = f"Async proxy for {endpoint_name} endpoint via gateway"
            return async_proxy_method

        else:

            def sync_proxy_method(**kwargs):
                # Validate input if schema is available
                if hasattr(endpoint_schema, "input_schema") and endpoint_schema.input_schema is not None:
                    try:
                        payload = endpoint_schema.input_schema(**kwargs).model_dump()
                    except Exception:
                        # Fallback to raw kwargs if validation fails
                        payload = kwargs
                else:
                    payload = kwargs

                # Make sync HTTP request (always POST for service endpoints)
                response = requests.post(endpoint_url, json=payload, timeout=60)

                if response.status_code != 200:
                    raise RuntimeError(f"Gateway proxy request failed: {response.text}")

                # Parse response
                try:
                    result = response.json()
                except Exception:
                    result = {"success": True}  # Default for empty responses

                # Validate output if schema is available
                if hasattr(endpoint_schema, "output_schema") and endpoint_schema.output_schema is not None:
                    try:
                        return endpoint_schema.output_schema(**result)
                    except Exception:
                        # Fallback to raw result if validation fails
                        return result
                else:
                    return result

            sync_proxy_method.__name__ = endpoint_name
            sync_proxy_method.__doc__ = f"Sync proxy for {endpoint_name} endpoint via gateway"
            return sync_proxy_method

    def __getattribute__(self, attr_name):
        """Handle property access by routing through the gateway."""
        # Always allow access to our internal attributes using object.__getattribute__
        internal_attrs = {
            "gateway_url",
            "app_name",
            "original_cm",
            "_service_endpoints",
            "_generate_proxy_methods",
            "_extract_service_endpoints",
            "_infer_endpoints_from_methods",
            "_create_proxy_method",
            "__class__",
            "__dict__",
        }

        if attr_name in internal_attrs:
            return object.__getattribute__(self, attr_name)

        # Check if this is a dynamically created proxy method (stored in instance __dict__)
        instance_dict = object.__getattribute__(self, "__dict__")
        if attr_name in instance_dict:
            return object.__getattribute__(self, attr_name)

        # For all other attributes, route through the gateway
        # This includes properties, methods, and any other attributes
        try:
            # Make a GET request to the gateway for property access
            endpoint_url = f"{self.gateway_url}/{self.app_name}/{attr_name}"
            response = requests.get(endpoint_url, timeout=60)

            if response.status_code == 200:
                try:
                    return response.json()
                except Exception:
                    return response.text
            else:
                # If GET fails, try POST (for methods that might be called as properties)
                response = requests.post(endpoint_url, timeout=60)
                if response.status_code == 200:
                    try:
                        return response.json()
                    except Exception:
                        return response.text
                else:
                    raise AttributeError(
                        f"Gateway request failed for '{attr_name}': {response.status_code} - {response.text}"
                    )

        except requests.RequestException as e:
            raise AttributeError(f"Gateway request failed for '{attr_name}': {e}")

    def __getattr__(self, attr_name):
        """Fallback for attribute access when __getattribute__ doesn't find it."""
        # This should rarely be called due to our __getattribute__ implementation
        # Use object.__getattribute__ to avoid recursion when accessing __class__
        class_name = object.__getattribute__(self, "__class__").__name__
        raise AttributeError(f"'{class_name}' object has no attribute '{attr_name}'")

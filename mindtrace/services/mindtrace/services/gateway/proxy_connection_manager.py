import inspect
from functools import wraps

import requests
from urllib3.util.url import Url

from mindtrace.services.core.connection_manager import ConnectionManager


class ProxyConnectionManager:
    """A proxy that forwards requests through the gateway instead of directly through the wrapped connection manager."""

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

    def __getattribute__(self, attr_name):
        """Handles both properties dynamically without recursion issues."""
        if attr_name in ["gateway_url", "app_name", "original_cm"]:
            return object.__getattribute__(self, attr_name)

        original_cm = object.__getattribute__(self, "original_cm")

        if hasattr(type(original_cm), attr_name):
            attr = getattr(type(original_cm), attr_name)

            if isinstance(attr, property):
                endpoint = f"{self.gateway_url}/{self.app_name}/{attr_name}"
                response = requests.get(endpoint, timeout=60)
                if response.status_code == 200:
                    return response.json()
                raise RuntimeError(f"Failed to get property '{attr_name}': {response.text}")

        # If not found, delegate to `__getattr__()` for method resolution
        return object.__getattribute__(self, attr_name)

    def __getattr__(self, method_name):
        """Intercepts method calls and routes them through the gateway."""
        return self.__create_proxy_method(method_name)

    def __create_proxy_method(self, method_name):
        """Helper function to create a proxy method that routes requests through the Gateway."""
        original_cm = object.__getattribute__(self, "original_cm")

        if not hasattr(original_cm, method_name):
            raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{method_name}'")

        original_method = getattr(original_cm, method_name)

        if not callable(original_method):
            raise AttributeError(f"'{self.__class__.__name__}' object has no callable attribute '{method_name}'")

        # Detect whether the method should use GET or POST based on its signature
        signature = inspect.signature(original_method)
        requires_arguments = any(param.default == inspect.Parameter.empty for param in signature.parameters.values())

        @wraps(original_method)
        def wrapped_method(*args, **kwargs):
            """Wraps the original method but reroutes the request through the gateway."""
            endpoint = f"{self.gateway_url}/{self.app_name}/{method_name}"

            if requires_arguments:
                # If method requires arguments, use POST
                payload = kwargs if kwargs else (args[0] if args else {})
                response = requests.post(endpoint, json=payload, timeout=60)
            else:
                # If method has no arguments, use GET
                response = requests.get(endpoint, timeout=60)

            if response.status_code == 200:
                return response.json()
            raise RuntimeError(f"Gateway proxy request failed: {response.text}")

        return wrapped_method

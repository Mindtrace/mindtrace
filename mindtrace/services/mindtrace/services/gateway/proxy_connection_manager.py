import inspect
from functools import wraps
from typing import Dict, Any, Callable

import httpx
from fastapi import HTTPException
import requests
from urllib3.util.url import Url

from mindtrace.core import TaskSchema
from mindtrace.services import ConnectionManager


class ProxyConnectionManager:
    """A proxy that forwards requests through the gateway instead of directly through the wrapped connection manager.
    
    This class creates proxy methods based on TaskSchemas, providing proper input/output validation
    and consistent behavior with auto-generated connection managers.
    """

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
        
        # Extract service endpoints and their schemas
        service_endpoints = self._extract_service_endpoints(original_cm)
        object.__setattr__(self, "_service_endpoints", service_endpoints)
        
        # Generate proxy methods for all endpoints
        self._generate_proxy_methods()

    def _extract_service_endpoints(self, original_cm: ConnectionManager) -> Dict[str, TaskSchema]:
        """Extract service endpoints and their TaskSchemas from the connection manager.
        
        This method tries multiple approaches to get the endpoint information:
        1. From the connection manager class's _service_endpoints (set by generate_connection_manager)
        2. From the original service class's _endpoints attribute
        3. Fallback to method introspection (less reliable)
        """
        # Try to get endpoints from connection manager class (set by generate_connection_manager)
        if hasattr(original_cm.__class__, '_service_endpoints'):
            return original_cm.__class__._service_endpoints
        
        # Try to get from the service class if available
        if hasattr(original_cm, '_service_class'):
            service_class = original_cm._service_class
            if hasattr(service_class, '_endpoints'):
                return service_class._endpoints
        
        # Last resort: infer from methods (less reliable)
        return self._infer_endpoints_from_methods(original_cm)
    
    def _infer_endpoints_from_methods(self, original_cm: ConnectionManager) -> Dict[str, TaskSchema]:
        """Fallback method to infer endpoints from connection manager methods."""
        endpoints = {}
        
        # Get all callable methods from the connection manager
        for attr_name in dir(original_cm):
            if not attr_name.startswith('_') and attr_name not in ['url', 'shutdown', 'astatus']:
                attr = getattr(original_cm, attr_name)
                if callable(attr) and not attr_name.startswith('a'):  # Skip async versions
                    # Create a basic TaskSchema without input/output validation
                    endpoints[attr_name] = TaskSchema(
                        name=attr_name,
                        input_schema=None,
                        output_schema=None
                    )
        
        return endpoints
    
    def _generate_proxy_methods(self):
        """Generate proxy methods for all endpoints based on their TaskSchemas."""
        service_endpoints = object.__getattribute__(self, "_service_endpoints")
        
        # Handle case where service_endpoints might be a Mock (in unit tests)
        try:
            # Test if we can actually iterate over items
            list(service_endpoints.items())
        except (TypeError, AttributeError):
            return
        
        for endpoint_name, task_schema in service_endpoints.items():
            # Skip system endpoints that shouldn't be proxied
            if endpoint_name in ['shutdown', 'status', 'heartbeat', 'endpoints', 'server_id', 'pid_file']:
                continue
                
            # Create sync and async proxy methods
            sync_method = self._create_proxy_method(endpoint_name, task_schema, is_async=False)
            async_method = self._create_proxy_method(endpoint_name, task_schema, is_async=True)
            
            # Store methods in instance dict for __getattribute__ to find
            if not hasattr(self, '__dict__'):
                object.__setattr__(self, '__dict__', {})
            
            self.__dict__[endpoint_name] = sync_method
            self.__dict__[f'a{endpoint_name}'] = async_method
    
    def _create_proxy_method(self, endpoint_name: str, task_schema: TaskSchema, is_async: bool = False) -> Callable:
        """Create a proxy method for a specific endpoint."""
        
        if is_async:
            async def proxy_method(validate_input: bool = True, validate_output: bool = False, **kwargs):
                return await self._make_async_request(endpoint_name, task_schema, validate_input, validate_output, **kwargs)
            
            proxy_method.__name__ = f'a{endpoint_name}'
            proxy_method.__doc__ = f"Async version: Calls the `{endpoint_name}` endpoint through the gateway"
        else:
            def proxy_method(validate_input: bool = True, validate_output: bool = False, **kwargs):
                return self._make_sync_request(endpoint_name, task_schema, validate_input, validate_output, **kwargs)
            
            proxy_method.__name__ = endpoint_name
            proxy_method.__doc__ = f"Calls the `{endpoint_name}` endpoint through the gateway"
        
        return proxy_method
    
    def _make_sync_request(self, endpoint_name: str, task_schema: TaskSchema, 
                          validate_input: bool, validate_output: bool, **kwargs) -> Any:
        """Make a synchronous request to the gateway."""
        # Input validation
        if validate_input and task_schema.input_schema is not None:
            try:
                payload = task_schema.input_schema(**kwargs).model_dump()
            except Exception:
                # Fallback to raw kwargs if validation fails
                payload = kwargs
        else:
            payload = kwargs
        
        # Make request
        endpoint_url = f"{self.gateway_url}/{self.app_name}/{endpoint_name}"
        response = requests.post(endpoint_url, json=payload, timeout=60)
        
        if response.status_code != 200:
            raise RuntimeError(f"Gateway proxy request failed for '{endpoint_name}': {response.status_code} - {response.text}")
        
        # Parse response
        try:
            result = response.json()
        except Exception:
            result = {"success": True}  # Default for empty responses
        
        # Output validation
        if validate_output and task_schema.output_schema is not None:
            try:
                return task_schema.output_schema(**result)
            except Exception:
                # Fallback to raw result if validation fails
                return result
        
        return result
    
    async def _make_async_request(self, endpoint_name: str, task_schema: TaskSchema,
                                validate_input: bool, validate_output: bool, **kwargs) -> Any:
        """Make an asynchronous request to the gateway."""
        # Input validation
        if validate_input and task_schema.input_schema is not None:
            try:
                payload = task_schema.input_schema(**kwargs).model_dump()
            except Exception:
                # Fallback to raw kwargs if validation fails
                payload = kwargs
        else:
            payload = kwargs
        
        # Make async request
        endpoint_url = f"{self.gateway_url}/{self.app_name}/{endpoint_name}"
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(endpoint_url, json=payload)
        
        if response.status_code != 200:
            raise HTTPException(response.status_code, response.text)
        
        # Parse response
        try:
            result = response.json()
        except Exception:
            result = {"success": True}  # Default for empty responses
        
        # Output validation
        if validate_output and task_schema.output_schema is not None:
            try:
                return task_schema.output_schema(**result)
            except Exception:
                # Fallback to raw result if validation fails
                return result
        
        return result

    def __getattribute__(self, attr_name):
        """Handles attribute access with proper delegation."""
        # Internal attributes - access directly
        internal_attrs = {
            'gateway_url', 'app_name', 'original_cm', '_service_endpoints', 
            '_generate_proxy_methods', '_extract_service_endpoints', 
            '_infer_endpoints_from_methods', '_create_proxy_method',
            '_make_sync_request', '_make_async_request',
            '__class__', '__dict__'
        }
        
        if attr_name in internal_attrs:
            return object.__getattribute__(self, attr_name)
        
        # Check if this is a dynamically created proxy method (stored in instance __dict__)
        try:
            instance_dict = object.__getattribute__(self, "__dict__")
            if attr_name in instance_dict:
                return object.__getattribute__(self, attr_name)
        except AttributeError:
            pass
        
        # Check if this is a property on the original connection manager
        original_cm = object.__getattribute__(self, "original_cm")
        if hasattr(type(original_cm), attr_name):
            attr = getattr(type(original_cm), attr_name)
            if isinstance(attr, property):
                # Handle properties by making a GET request to the gateway
                endpoint_url = f"{self.gateway_url}/{self.app_name}/{attr_name}"
                response = requests.get(endpoint_url, timeout=60)
                if response.status_code == 200:
                    return response.json()
                raise RuntimeError(f"Failed to get property '{attr_name}': {response.text}")
        
        # If not found anywhere, raise AttributeError
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{attr_name}'")

    def __getattr__(self, method_name):
        """Fallback method for attributes not found in __getattribute__."""
        # This handles any remaining cases where methods weren't pre-generated
        original_cm = object.__getattribute__(self, "original_cm")
        
        if not hasattr(original_cm, method_name):
            raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{method_name}'")
        
        original_method = getattr(original_cm, method_name)
        if not callable(original_method):
            raise AttributeError(f"'{self.__class__.__name__}' object has no callable attribute '{method_name}'")
        
        # Analyze method signature to determine if it has required parameters
        import inspect
        try:
            signature = inspect.signature(original_method)
            has_required_params = any(
                param.default is inspect.Parameter.empty and param.kind not in [
                    inspect.Parameter.VAR_POSITIONAL, 
                    inspect.Parameter.VAR_KEYWORD
                ]
                for param in signature.parameters.values()
            )
        except (ValueError, TypeError):
            # If we can't analyze the signature, assume it has required params
            has_required_params = True
        
        # Create a basic proxy method without schema validation (fallback)
        @wraps(original_method)
        def fallback_proxy_method(*args, **kwargs):
            endpoint_url = f"{self.gateway_url}/{self.app_name}/{method_name}"
            
            # Determine HTTP method and payload based on signature analysis
            if not has_required_params and not args and not kwargs:
                # Method has no required params and no args provided -> use GET
                response = requests.get(endpoint_url, timeout=60)
            else:
                # Method has required params or args provided -> use POST
                # Only use kwargs for payload - ignore positional args for robustness
                payload = kwargs if kwargs else {}
                
                response = requests.post(endpoint_url, json=payload, timeout=60)
            
            if response.status_code == 200:
                return response.json()
            raise RuntimeError(f"Gateway proxy request failed for '{method_name}': {response.status_code} - {response.text}")
        
        return fallback_proxy_method

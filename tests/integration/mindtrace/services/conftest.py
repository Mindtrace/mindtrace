import pytest_asyncio

from mindtrace.services import Gateway
from mindtrace.services.sample.echo_service import EchoService
from mindtrace.services.sample.echo_mcp import EchoService as echo_mcp_service

@pytest_asyncio.fixture(scope="session")
async def echo_service_manager():
    """Launch EchoService and provide a connection manager for testing.

    This fixture uses the EchoService.launch context manager to properly start and stop the service, yielding a 
    connection manager that tests can use to interact with the running service.
    
    Session-scoped for performance - service is launched once and reused across all tests in the session.
    """
    try:
        with EchoService.launch(url="http://localhost:8090", timeout=30) as cm:
            yield cm
    except Exception as e:
        print(f"Service launch failed: {e}")
        raise


@pytest_asyncio.fixture(scope="session")
async def gateway_manager():
    """Launch Gateway and provide a connection manager for testing.

    This fixture uses the Gateway.launch context manager to properly start and stop the gateway, yielding a connection 
    manager that tests can use to interact with the running gateway.
    
    Session-scoped for performance - gateway is launched once and reused across all tests in the session.
    """
    try:
        with Gateway.launch(url="http://localhost:8091", timeout=30) as cm:
            yield cm
    except Exception as e:
        print(f"Gateway launch failed: {e}")
        raise


@pytest_asyncio.fixture(scope="session")
async def echo_service_for_gateway():
    """Launch EchoService on a different port for Gateway integration testing.
    
    This runs EchoService on port 8092 to avoid conflicts with the main echo_service_manager fixture.
    
    Session-scoped for performance - service is launched once and reused across all tests in the session.
    """
    try:
        with EchoService.launch(url="http://localhost:8092", timeout=30) as cm:
            yield cm
    except Exception as e:
        print(f"Echo service for gateway launch failed: {e}")
        raise


@pytest_asyncio.fixture(scope="session")
async def echo_mcp_manager():
    """Launch EchoService for MCP integration testing on a dedicated port.
    This fixture can be used in MCP-related integration tests to ensure a clean, isolated service instance.
    """
    try:
        with echo_mcp_service.launch(url="http://localhost:8093", timeout=30) as cm:
            yield cm
    except Exception as e:
        print(f"Echo MCP service launch failed: {e}")
        raise

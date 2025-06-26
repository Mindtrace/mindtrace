import pytest
import pytest_asyncio

from mindtrace.services.sample.echo_service import EchoService


@pytest_asyncio.fixture
async def echo_service_manager():
    """
    Launch EchoService and provide a connection manager for testing.
    
    This fixture uses the EchoService.launch context manager to properly
    start and stop the service, yielding a connection manager that tests
    can use to interact with the running service.
    """
    try:
        with EchoService.launch(url="http://localhost:8090", timeout=15) as cm:
            yield cm
    except Exception as e:
        # If service launch fails, yield None so tests can handle gracefully
        print(f"Service launch failed: {e}")
        yield None

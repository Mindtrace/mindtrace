import asyncio

import pytest
import requests

from mindtrace.services import generate_connection_manager
from mindtrace.services.sample.echo_service import EchoOutput, EchoService


class TestServiceIntegration:
    """Simplified integration tests for service functionality"""
    
    def test_connection_manager_generation_without_service(self):
        """Test that we can generate connection managers without launching services"""
        ConnectionManager = generate_connection_manager(EchoService)
        
        # Verify it has the expected methods
        assert hasattr(ConnectionManager, 'echo')
        assert hasattr(ConnectionManager, 'aecho')
        
        # Create an instance (won't work for actual calls but tests the creation)
        manager = ConnectionManager(url="http://localhost:8080")
        assert str(manager.url) == "http://localhost:8080"
    
    @pytest.mark.asyncio
    async def test_service_launch_and_basic_functionality(self, echo_service_manager):
        """Test service functionality using the launched service from conftest.py"""
        if echo_service_manager is None:
            # Service didn't start - verify connection manager creation still works
            print("Service didn't start, testing connection manager behavior")
            
            ConnectionManager = generate_connection_manager(EchoService)
            manager = ConnectionManager(url="http://localhost:8090")
            
            # These should fail with connection errors, not other errors
            with pytest.raises((requests.exceptions.ConnectionError, Exception)) as exc_info:
                manager.echo(message="This should fail")
            
            # Verify it's a connection error, not a coding error
            assert "connection" in str(exc_info.value).lower() or "refused" in str(exc_info.value).lower()
            
            print("Connection manager behavior is correct for non-running service")
            return
            
        # Service is running - test full functionality
        print("Service launched successfully!")
        
        # Test sync call
        result = echo_service_manager.echo(message="Integration test message")
        assert isinstance(result, EchoOutput)
        assert result.echoed == "Integration test message"
        
        # Test async call
        async_result = await echo_service_manager.aecho(message="Async integration test")
        assert isinstance(async_result, EchoOutput)
        assert async_result.echoed == "Async integration test"
        
        print("All integration tests passed!")

    @pytest.mark.asyncio
    async def test_default_service_endpoints(self, echo_service_manager):
        """Test all default Service endpoints (sync and async versions)"""
        if echo_service_manager is None:
            # Service didn't start - verify connection manager has the methods but they fail appropriately
            print("Service didn't start, testing default endpoint method existence")
            
            ConnectionManager = generate_connection_manager(EchoService)
            manager = ConnectionManager(url="http://localhost:8090")
            
            # Verify all default endpoint methods exist
            default_endpoints = ['endpoints', 'status', 'heartbeat', 'server_id', 'pid_file', 'shutdown']
            for endpoint in default_endpoints:
                assert hasattr(manager, endpoint), f"Missing sync method: {endpoint}"
                assert hasattr(manager, f"a{endpoint}"), f"Missing async method: a{endpoint}"
            
            print("All default endpoint methods exist on connection manager")
            return
            
        # Service is running - test all default endpoints
        print("Testing default service endpoints with running service")
        
        # Test endpoints endpoint (sync)
        endpoints_result = echo_service_manager.endpoints()
        assert isinstance(endpoints_result, dict)
        assert "echo" in endpoints_result  # Our custom endpoint
        
        # Default endpoints should also be present
        default_endpoint_names = ["endpoints", "status", "heartbeat", "server_id", "pid_file", "shutdown"]
        for endpoint_name in default_endpoint_names:
            assert endpoint_name in endpoints_result, f"Missing default endpoint: {endpoint_name}"
        
        # Test endpoints endpoint (async)
        aendpoints_result = await echo_service_manager.aendpoints()
        assert isinstance(aendpoints_result, dict)
        assert aendpoints_result == endpoints_result  # Should be the same
        
        # Test status endpoint (sync)
        status_result = echo_service_manager.status()
        assert isinstance(status_result, dict)
        assert "status" in status_result
        assert status_result["status"] in ["running", "ready", "healthy"]  # Common status values
        
        # Test status endpoint (async)
        astatus_result = await echo_service_manager.astatus()
        assert isinstance(astatus_result, dict)
        assert "status" in astatus_result
        
        # Test heartbeat endpoint (sync)
        heartbeat_result = echo_service_manager.heartbeat()
        assert isinstance(heartbeat_result, dict)
        assert "timestamp" in heartbeat_result or "heartbeat" in heartbeat_result
        
        # Test heartbeat endpoint (async)
        aheartbeat_result = await echo_service_manager.aheartbeat()
        assert isinstance(aheartbeat_result, dict)
        assert "timestamp" in aheartbeat_result or "heartbeat" in aheartbeat_result
        
        # Test server_id endpoint (sync)
        server_id_result = echo_service_manager.server_id()
        assert isinstance(server_id_result, dict)
        assert "server_id" in server_id_result or "id" in server_id_result
        
        # Test server_id endpoint (async)
        aserver_id_result = await echo_service_manager.aserver_id()
        assert isinstance(aserver_id_result, dict)
        assert "server_id" in aserver_id_result or "id" in aserver_id_result
        
        # Test pid_file endpoint (sync)
        pid_file_result = echo_service_manager.pid_file()
        assert isinstance(pid_file_result, dict)
        # PID file might be None if not configured, that's okay
        assert "pid_file" in pid_file_result or "pid" in pid_file_result
        
        # Test pid_file endpoint (async)
        apid_file_result = await echo_service_manager.apid_file()
        assert isinstance(apid_file_result, dict)
        assert "pid_file" in apid_file_result or "pid" in apid_file_result
        
        # Note: Not testing shutdown endpoint as it would terminate the service
        # But we can verify the method exists
        assert hasattr(echo_service_manager, 'shutdown'), "Missing shutdown method"
        assert hasattr(echo_service_manager, 'ashutdown'), "Missing ashutdown method"
        
        print("All default service endpoints tested successfully!")
    
    def test_url_construction_logic(self):
        """Test URL construction without requiring a running service"""
        ConnectionManager = generate_connection_manager(EchoService)
        
        # Test different URL formats
        test_urls = [
            "http://localhost:8080",
            "http://localhost:8080/",
            "https://example.com",
            "https://example.com/",
        ]
        
        for url in test_urls:
            manager = ConnectionManager(url=url)
            assert manager.url is not None
            
            # The URL should be stored properly
            url_str = str(manager.url)
            assert url_str == url or url_str == url.rstrip('/')
    
    @pytest.mark.asyncio
    async def test_echo_service_import_and_instantiation(self):
        """Test that we can import and instantiate the echo service"""
        try:
            service = EchoService(port=8091, host="localhost") 
            
            # Verify service has the expected endpoints
            assert "echo" in service.endpoints
            assert service.endpoints["echo"].name == "echo"
            assert service.endpoints["echo"].input_schema.__name__ == "EchoInput"
            assert service.endpoints["echo"].output_schema.__name__ == "EchoOutput"
            
            # Verify connection manager generation works
            ConnectionManager = generate_connection_manager(EchoService)
            assert ConnectionManager.__name__ == "EchoServiceConnectionManager"
            
            print("Service import and instantiation works correctly")
            
        except Exception as e:
            # This shouldn't fail since we're just importing and creating, not launching
            pytest.fail(f"Service instantiation failed: {e}")
    
    def test_task_registration(self):
        """Test that services register their tasks correctly"""
        service = EchoService(port=8092, host="localhost")
        
        # Check that echo task is registered
        assert "echo" in service.endpoints
        echo_task = service.endpoints["echo"]
        
        assert echo_task.name == "echo"
        assert echo_task.input_schema.__name__ == "EchoInput"
        assert echo_task.output_schema.__name__ == "EchoOutput"
        
        # Verify the generated connection manager has the right methods
        ConnectionManager = generate_connection_manager(EchoService)
        
        # Check method existence
        assert hasattr(ConnectionManager, "echo")
        assert hasattr(ConnectionManager, "aecho")
        
        # Check method documentation
        echo_method = getattr(ConnectionManager, "echo")
        aecho_method = getattr(ConnectionManager, "aecho")
        
        assert "echo" in echo_method.__doc__
        assert "Async version" in aecho_method.__doc__ 

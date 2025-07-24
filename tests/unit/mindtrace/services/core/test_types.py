import json
from uuid import UUID, uuid4

import pytest

from mindtrace.services.core.types import (
    EndpointsOutput,
    EndpointsSchema,
    Heartbeat,
    HeartbeatOutput,
    HeartbeatSchema,
    PIDFileOutput,
    PIDFileSchema,
    ServerIDOutput,
    ServerIDSchema,
    ServerStatus,
    ShutdownOutput,
    ShutdownSchema,
    StatusOutput,
    StatusSchema,
)


class TestServerStatus:
    """Test suite for ServerStatus enum."""

    def test_server_status_values(self):
        """Test that ServerStatus enum has expected values."""
        assert ServerStatus.DOWN.value == "Down"
        assert ServerStatus.LAUNCHING.value == "Launching"
        assert ServerStatus.FAILED_TO_LAUNCH.value == "FailedToLaunch"
        assert ServerStatus.AVAILABLE.value == "Available"
        assert ServerStatus.STOPPING.value == "Stopping"

    def test_server_status_members(self):
        """Test that all expected ServerStatus members exist."""
        expected_members = {"DOWN", "LAUNCHING", "FAILED_TO_LAUNCH", "AVAILABLE", "STOPPING"}
        actual_members = {status.name for status in ServerStatus}
        assert actual_members == expected_members

    def test_server_status_string_representation(self):
        """Test string representation of ServerStatus values."""
        assert str(ServerStatus.DOWN) == "ServerStatus.DOWN"
        assert str(ServerStatus.AVAILABLE) == "ServerStatus.AVAILABLE"


class TestHeartbeat:
    """Test suite for Heartbeat dataclass."""

    def test_heartbeat_default_initialization(self):
        """Test Heartbeat initialization with default values."""
        heartbeat = Heartbeat()

        assert heartbeat.status == ServerStatus.DOWN
        assert heartbeat.server_id is None
        assert heartbeat.message is None
        assert heartbeat.details is None

    def test_heartbeat_full_initialization(self):
        """Test Heartbeat initialization with all parameters."""
        server_id = uuid4()
        details = {"custom": "data"}

        heartbeat = Heartbeat(
            status=ServerStatus.AVAILABLE, server_id=server_id, message="Server is running", details=details
        )

        assert heartbeat.status == ServerStatus.AVAILABLE
        assert heartbeat.server_id == server_id
        assert heartbeat.message == "Server is running"
        assert heartbeat.details == details

    def test_heartbeat_str_with_dict_details(self):
        """Test __str__ method with dict details."""
        server_id = uuid4()
        details = {"nodes": 3, "memory": "8GB", "status": "healthy"}

        heartbeat = Heartbeat(
            status=ServerStatus.AVAILABLE, server_id=server_id, message="Cluster is running", details=details
        )

        result = str(heartbeat)

        # Check that all components are present
        assert f"Server ID: {server_id}" in result
        assert "Status: ServerStatus.AVAILABLE" in result
        assert "Message: Cluster is running" in result
        assert "Details:" in result

        # Check that JSON formatting is applied for dict details
        assert json.dumps(details, indent=4) in result
        assert '"nodes": 3' in result
        assert '"memory": "8GB"' in result

    def test_heartbeat_str_with_non_dict_details(self):
        """Test __str__ method with non-dict details."""
        server_id = uuid4()
        details = "Simple string details"

        heartbeat = Heartbeat(
            status=ServerStatus.LAUNCHING, server_id=server_id, message="Starting up", details=details
        )

        result = str(heartbeat)

        # Check that all components are present
        assert f"Server ID: {server_id}" in result
        assert "Status: ServerStatus.LAUNCHING" in result
        assert "Message: Starting up" in result
        assert f"Details: {details}" in result

        # Should not have JSON formatting for non-dict details
        assert "{\n" not in result  # No JSON object formatting

    def test_heartbeat_str_with_none_values(self):
        """Test __str__ method with None values."""
        heartbeat = Heartbeat()

        result = str(heartbeat)

        assert "Server ID: None" in result
        assert "Status: ServerStatus.DOWN" in result
        assert "Message: None" in result
        assert "Details: None" in result

    def test_heartbeat_str_with_list_details(self):
        """Test __str__ method with list details (non-dict)."""
        server_id = uuid4()
        details = ["item1", "item2", "item3"]

        heartbeat = Heartbeat(
            status=ServerStatus.STOPPING, server_id=server_id, message="Shutting down", details=details
        )

        result = str(heartbeat)

        assert f"Server ID: {server_id}" in result
        assert "Status: ServerStatus.STOPPING" in result
        assert "Message: Shutting down" in result
        assert f"Details: {details}" in result

    def test_heartbeat_str_with_complex_dict_details(self):
        """Test __str__ method with complex nested dict details."""
        server_id = uuid4()
        details = {
            "services": {"web": {"status": "running", "port": 8080}, "db": {"status": "running", "port": 5432}},
            "metrics": {"cpu": 45.2, "memory": 78.5, "connections": 150},
        }

        heartbeat = Heartbeat(
            status=ServerStatus.AVAILABLE, server_id=server_id, message="All systems operational", details=details
        )

        result = str(heartbeat)

        # Check basic structure
        assert f"Server ID: {server_id}" in result
        assert "Status: ServerStatus.AVAILABLE" in result
        assert "Message: All systems operational" in result

        # Check that nested JSON structure is properly formatted
        formatted_json = json.dumps(details, indent=4)
        assert formatted_json in result
        assert '"services"' in result
        assert '"web"' in result
        assert '"status": "running"' in result

    def test_heartbeat_str_with_empty_dict_details(self):
        """Test __str__ method with empty dict details."""
        server_id = uuid4()
        details = {}

        heartbeat = Heartbeat(
            status=ServerStatus.FAILED_TO_LAUNCH, server_id=server_id, message="Launch failed", details=details
        )

        result = str(heartbeat)

        assert f"Server ID: {server_id}" in result
        assert "Status: ServerStatus.FAILED_TO_LAUNCH" in result
        assert "Message: Launch failed" in result
        assert "Details: {}" in result


class TestOutputModels:
    """Test suite for output model classes."""

    def test_endpoints_output(self):
        """Test EndpointsOutput model."""
        endpoints = ["echo", "status", "heartbeat"]
        output = EndpointsOutput(endpoints=endpoints)

        assert output.endpoints == endpoints
        assert isinstance(output.endpoints, list)

    def test_status_output(self):
        """Test StatusOutput model."""
        output = StatusOutput(status=ServerStatus.AVAILABLE)

        assert output.status == ServerStatus.AVAILABLE
        assert isinstance(output.status, ServerStatus)

    def test_heartbeat_output(self):
        """Test HeartbeatOutput model."""
        heartbeat = Heartbeat(status=ServerStatus.AVAILABLE)
        output = HeartbeatOutput(heartbeat=heartbeat)

        assert output.heartbeat == heartbeat
        assert isinstance(output.heartbeat, Heartbeat)

    def test_server_id_output(self):
        """Test ServerIDOutput model."""
        server_id = uuid4()
        output = ServerIDOutput(server_id=server_id)

        assert output.server_id == server_id
        assert isinstance(output.server_id, UUID)

    def test_pid_file_output(self):
        """Test PIDFileOutput model."""
        pid_file = "/var/run/service.pid"
        output = PIDFileOutput(pid_file=pid_file)

        assert output.pid_file == pid_file
        assert isinstance(output.pid_file, str)

    def test_shutdown_output(self):
        """Test ShutdownOutput model."""
        output = ShutdownOutput(shutdown=True)

        assert output.shutdown is True
        assert isinstance(output.shutdown, bool)

        output_false = ShutdownOutput(shutdown=False)
        assert output_false.shutdown is False


class TestIntegration:
    """Integration tests for types working together."""

    def test_status_output_with_all_server_statuses(self):
        """Test StatusOutput with all possible server statuses."""
        for status in ServerStatus:
            output = StatusOutput(status=status)
            assert output.status == status

    def test_heartbeat_output_with_different_heartbeats(self):
        """Test HeartbeatOutput with different heartbeat configurations."""
        # Test with minimal heartbeat
        minimal_heartbeat = Heartbeat()
        output1 = HeartbeatOutput(heartbeat=minimal_heartbeat)
        assert output1.heartbeat.status == ServerStatus.DOWN

        # Test with full heartbeat
        server_id = uuid4()
        full_heartbeat = Heartbeat(
            status=ServerStatus.AVAILABLE, server_id=server_id, message="All good", details={"cpu": 50}
        )
        output2 = HeartbeatOutput(heartbeat=full_heartbeat)
        assert output2.heartbeat.status == ServerStatus.AVAILABLE
        assert output2.heartbeat.server_id == server_id

    def test_pydantic_validation(self):
        """Test that Pydantic validation works correctly for output models."""
        # Test that invalid types raise validation errors
        with pytest.raises(Exception):  # Pydantic validation error
            EndpointsOutput(endpoints="not a list") # type: ignore

        with pytest.raises(Exception):  # Pydantic validation error
            ServerIDOutput(server_id="not a uuid") # type: ignore

        with pytest.raises(Exception):  # Pydantic validation error
            ShutdownOutput(shutdown="not a boolean") # type: ignore

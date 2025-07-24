from unittest.mock import patch

import pytest

from mindtrace.services.sample.echo_service import EchoInput, EchoOutput, EchoService, echo_task


class TestEchoInput:
    """Test suite for EchoInput model."""

    def test_echo_input_creation(self):
        """Test EchoInput model creation with valid data."""
        input_data = EchoInput(message="Hello World")
        assert input_data.message == "Hello World"

    def test_echo_input_validation(self):
        """Test EchoInput model validation."""
        # Test valid input
        valid_input = EchoInput(message="test")
        assert isinstance(valid_input.message, str)

        # Test that message field is required
        with pytest.raises(ValueError):
            EchoInput() # type: ignore

    def test_echo_input_serialization(self):
        """Test EchoInput model serialization."""
        input_data = EchoInput(message="test message")
        serialized = input_data.model_dump()
        assert serialized == {"message": "test message", "delay": 0.0}

    def test_echo_input_with_delay(self):
        """Test EchoInput model with delay parameter."""
        input_data = EchoInput(message="test message", delay=0.5)
        assert input_data.message == "test message"
        assert input_data.delay == 0.5

        serialized = input_data.model_dump()
        assert serialized == {"message": "test message", "delay": 0.5}

    def test_echo_input_delay_validation(self):
        """Test EchoInput delay parameter validation."""
        # Test valid delay values
        valid_delays = [0.0, 0.1, 1.0, 5.0]
        for delay in valid_delays:
            input_data = EchoInput(message="test", delay=delay)
            assert input_data.delay == delay

        # Test negative delay (should be allowed as it's just a float)
        input_data = EchoInput(message="test", delay=-1.0)
        assert input_data.delay == -1.0


class TestEchoOutput:
    """Test suite for EchoOutput model."""

    def test_echo_output_creation(self):
        """Test EchoOutput model creation with valid data."""
        output_data = EchoOutput(echoed="Hello World")
        assert output_data.echoed == "Hello World"

    def test_echo_output_validation(self):
        """Test EchoOutput model validation."""
        # Test valid output
        valid_output = EchoOutput(echoed="test")
        assert isinstance(valid_output.echoed, str)

        # Test that echoed field is required
        with pytest.raises(ValueError):
            EchoOutput() # type: ignore

    def test_echo_output_serialization(self):
        """Test EchoOutput model serialization."""
        output_data = EchoOutput(echoed="echoed message")
        serialized = output_data.model_dump()
        assert serialized == {"echoed": "echoed message"}


class TestEchoService:
    """Test suite for EchoService class."""

    @patch("mindtrace.services.sample.echo_service.Service.__init__")
    def test_echo_service_initialization(self, mock_super_init):
        """Test EchoService initialization."""
        mock_super_init.return_value = None

        # Mock the add_endpoint method
        with patch.object(EchoService, "add_endpoint") as mock_add_endpoint:
            service = EchoService()

            # Verify parent constructor was called
            mock_super_init.assert_called_once()

            # Verify add_endpoint was called with correct parameters
            mock_add_endpoint.assert_called_once_with("echo", service.echo, schema=echo_task)

    @patch("mindtrace.services.sample.echo_service.Service.__init__")
    def test_echo_service_initialization_with_args(self, mock_super_init):
        """Test EchoService initialization with arguments."""
        mock_super_init.return_value = None

        with patch.object(EchoService, "add_endpoint") as mock_add_endpoint:
            service = EchoService("arg1", "arg2", kwarg1="value1", kwarg2="value2")

            # Verify parent constructor was called with arguments
            mock_super_init.assert_called_once_with("arg1", "arg2", kwarg1="value1", kwarg2="value2")

            # Verify add_endpoint was still called correctly
            mock_add_endpoint.assert_called_once_with("echo", service.echo, schema=echo_task)

    def test_echo_method_functionality(self):
        """Test the echo method functionality."""
        # Create service instance without calling __init__ to avoid mocking issues
        service = EchoService.__new__(EchoService)

        # Test the echo method directly
        input_data = EchoInput(message="Hello World")
        result = service.echo(input_data)

        # Verify the result
        assert isinstance(result, EchoOutput)
        assert result.echoed == "Hello World"

    def test_echo_method_with_different_messages(self):
        """Test echo method with various message inputs."""
        service = EchoService.__new__(EchoService)

        test_messages = [
            "Simple message",
            "Message with numbers 123",
            "Special chars !@#$%^&*()",
            "",  # Empty string
            "Very long message " * 100,
        ]

        for message in test_messages:
            input_data = EchoInput(message=message)
            result = service.echo(input_data)
            assert result.echoed == message

    @patch("time.sleep")
    def test_echo_method_with_delay(self, mock_sleep):
        """Test echo method with delay parameter."""
        service = EchoService.__new__(EchoService)

        # Test with no delay (default)
        input_data = EchoInput(message="test message")
        result = service.echo(input_data)
        assert result.echoed == "test message"
        mock_sleep.assert_not_called()

        # Test with delay
        mock_sleep.reset_mock()
        input_data = EchoInput(message="delayed message", delay=0.5)
        result = service.echo(input_data)
        assert result.echoed == "delayed message"
        mock_sleep.assert_called_once_with(0.5)

        # Test with zero delay (should not call sleep)
        mock_sleep.reset_mock()
        input_data = EchoInput(message="zero delay", delay=0.0)
        result = service.echo(input_data)
        assert result.echoed == "zero delay"
        mock_sleep.assert_not_called()

    @patch("mindtrace.services.sample.echo_service.Service.__init__")
    def test_echo_service_inheritance(self, mock_super_init):
        """Test that EchoService properly inherits from Service."""
        from mindtrace.services import Service

        mock_super_init.return_value = None

        with patch.object(EchoService, "add_endpoint"):
            service = EchoService()
            assert isinstance(service, Service)

    def test_echo_method_type_validation(self):
        """Test that echo method handles type validation correctly."""
        service = EchoService.__new__(EchoService)

        # Test with valid EchoInput
        valid_input = EchoInput(message="test")
        result = service.echo(valid_input)
        assert isinstance(result, EchoOutput)
        assert result.echoed == "test"

    @patch("mindtrace.services.sample.echo_service.Service.__init__")
    def test_echo_service_endpoint_configuration(self, mock_super_init):
        """Test that the echo endpoint is configured correctly."""
        mock_super_init.return_value = None

        with patch.object(EchoService, "add_endpoint") as mock_add_endpoint:
            service = EchoService()

            # Verify the endpoint configuration
            call_args = mock_add_endpoint.call_args
            assert call_args[0][0] == "echo"  # endpoint path
            assert call_args[0][1] == service.echo  # endpoint function
            assert call_args[1]["schema"] == echo_task  # schema parameter


class TestEchoServiceIntegration:
    """Integration tests for EchoService components working together."""

    def test_input_output_flow(self):
        """Test the complete input-to-output flow."""
        # Create input
        input_message = "Integration test message"
        echo_input = EchoInput(message=input_message)

        # Process through echo method
        service = EchoService.__new__(EchoService)
        echo_output = service.echo(echo_input)

        # Verify output
        assert echo_output.echoed == input_message
        assert isinstance(echo_output, EchoOutput)

    def test_schema_compatibility(self):
        """Test that the schema is compatible with the service methods."""
        # Verify schema input/output types match the method signature
        assert echo_task.input_schema == EchoInput
        assert echo_task.output_schema == EchoOutput

        # Test that we can create instances of the schema types
        test_input = EchoInput(message="test")
        assert isinstance(test_input, EchoInput)

        # Test method with schema-created input
        service = EchoService.__new__(EchoService)
        result = service.echo(test_input)
        assert isinstance(result, EchoOutput)

    @patch("mindtrace.services.sample.echo_service.Service.__init__")
    def test_service_with_mock_dependencies(self, mock_super_init):
        """Test EchoService with all dependencies mocked."""
        mock_super_init.return_value = None

        # Mock the Service class methods that might be called
        with patch.object(EchoService, "add_endpoint") as mock_add_endpoint:
            # Create service
            service = EchoService()

            # Verify initialization
            assert mock_super_init.called
            assert mock_add_endpoint.called

            # Test the core functionality still works
            test_input = EchoInput(message="mocked test")
            result = service.echo(test_input)
            assert result.echoed == "mocked test"

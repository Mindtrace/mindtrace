from unittest.mock import patch

import pytest

from mindtrace.services.samples.echo_mcp import (
    EchoInput,
    EchoOutput,
    EchoService,
    echo_task,
    reverse_message,
)


class TestEchoMcpModels:
    def test_echo_input_defaults(self):
        payload = EchoInput(message="hello")
        assert payload.model_dump() == {"message": "hello", "delay": 0.0}

    def test_echo_output_serialization(self):
        output = EchoOutput(echoed="world")
        assert output.model_dump() == {"echoed": "world"}


class TestEchoMcpHelpers:
    def test_reverse_message_reverses_text(self):
        result = reverse_message(EchoInput(message="mindtrace"))
        assert isinstance(result, EchoOutput)
        assert result.echoed == "ecartdnim"


class TestEchoMcpService:
    @patch("mindtrace.services.samples.echo_mcp.Service.__init__")
    def test_initialization_registers_endpoint_and_tool(self, mock_super_init):
        mock_super_init.return_value = None

        with patch.object(EchoService, "add_endpoint") as mock_add_endpoint:
            with patch.object(EchoService, "add_tool") as mock_add_tool:
                service = EchoService()

        mock_super_init.assert_called_once()
        mock_add_endpoint.assert_called_once_with("echo", service.echo, schema=echo_task, as_tool=True)
        mock_add_tool.assert_called_once_with("reverse_message", reverse_message)

    @patch("time.sleep")
    def test_echo_returns_message_and_honors_delay(self, mock_sleep):
        service = EchoService.__new__(EchoService)

        immediate = service.echo(EchoInput(message="hello"))
        delayed = service.echo(EchoInput(message="later", delay=0.25))

        assert immediate.echoed == "hello"
        assert delayed.echoed == "later"
        mock_sleep.assert_called_once_with(0.25)

    def test_schema_matches_models(self):
        assert echo_task.name == "echo"
        assert echo_task.input_schema is EchoInput
        assert echo_task.output_schema is EchoOutput

    def test_echo_input_requires_message(self):
        with pytest.raises(ValueError):
            EchoInput()  # type: ignore

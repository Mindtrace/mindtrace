"""Behavioral unit tests for core.exceptions."""

from mindtrace.registry.core.exceptions import RegistryObjectNotFound


class TestMissingObjectMessages:
    def test_message_is_unquoted_while_preserving_key_error_compatibility(self):
        message = "Object missing@1.0.0 not found"
        error = RegistryObjectNotFound(message)
        assert isinstance(error, KeyError)
        assert error.args == (message,)
        assert str(error) == message

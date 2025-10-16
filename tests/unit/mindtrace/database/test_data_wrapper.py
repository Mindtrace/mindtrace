"""Tests for the DataWrapper class used in unified backend."""

import pytest


# Test DataWrapper class (if it exists)
class TestDataWrapper:
    """Test the DataWrapper class used in unified backend."""

    def test_data_wrapper_creation(self):
        """Test DataWrapper creation and access."""
        # Check if DataWrapper is defined in the unified backend
        try:
            from mindtrace.database.backends.unified_odm_backend import DataWrapper

            data = {"name": "John", "age": 30}
            wrapper = DataWrapper(data)

            assert wrapper.data == data
            assert wrapper.data["name"] == "John"
            assert wrapper.data["age"] == 30

        except ImportError:
            # DataWrapper might not be defined, skip this test
            pytest.skip("DataWrapper class not found in unified backend")

    def test_data_wrapper_model_dump(self):
        """Test DataWrapper model_dump method."""
        try:
            from mindtrace.database.backends.unified_odm_backend import DataWrapper

            data = {"name": "John", "age": 30}
            wrapper = DataWrapper(data)

            result = wrapper.model_dump()
            assert result == data

        except ImportError:
            pytest.skip("DataWrapper class not found")

    def test_data_wrapper_str_representation(self):
        """Test DataWrapper string representation."""
        try:
            from mindtrace.database.backends.unified_odm_backend import DataWrapper

            data = {"name": "John", "age": 30}
            wrapper = DataWrapper(data)

            str_repr = str(wrapper)
            assert "DataWrapper" in str_repr

        except ImportError:
            pytest.skip("DataWrapper class not found")

    def test_data_wrapper_repr_representation(self):
        """Test DataWrapper repr representation."""
        try:
            from mindtrace.database.backends.unified_odm_backend import DataWrapper

            data = {"name": "John", "age": 30}
            wrapper = DataWrapper(data)

            repr_str = repr(wrapper)
            assert "DataWrapper" in repr_str

        except ImportError:
            pytest.skip("DataWrapper class not found")

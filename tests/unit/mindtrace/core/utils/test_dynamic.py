"""Unit tests for the dynamic utils module."""

import pytest

from mindtrace.core.utils.dynamic import dynamic_instantiation, get_class, instantiate_target


class TestDynamicInstantiation:
    """Test cases for dynamic_instantiation function."""

    def test_dynamic_instantiation_success(self):
        """Test successful dynamic instantiation of a class."""
        # Test with a simple class from a standard library
        result = dynamic_instantiation("datetime", "datetime", year=2024, month=1, day=1)
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 1

    def test_dynamic_instantiation_invalid_module(self):
        """Test dynamic instantiation with invalid module."""
        with pytest.raises(ImportError):
            dynamic_instantiation("nonexistent_module", "SomeClass")

    def test_dynamic_instantiation_invalid_class(self):
        """Test dynamic instantiation with invalid class name."""
        with pytest.raises(AttributeError):
            dynamic_instantiation("datetime", "NonexistentClass")


class TestInstantiateTarget:
    """Test cases for instantiate_target function."""

    def test_instantiate_target_success(self):
        """Test successful instantiation of a target object."""
        # Test with a simple class from a standard library
        result = instantiate_target("datetime.datetime", year=2024, month=1, day=1)
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 1

    def test_instantiate_target_invalid_format(self):
        """Test instantiation with invalid target format."""
        with pytest.raises(ValueError):
            instantiate_target("invalid_format")

    def test_instantiate_target_invalid_module(self):
        """Test instantiation with invalid module path."""
        with pytest.raises(ImportError):
            instantiate_target("nonexistent.module.Class")

    def test_instantiate_target_invalid_class(self):
        """Test instantiation with invalid class name."""
        with pytest.raises(AttributeError):
            instantiate_target("datetime.NonexistentClass")


class TestGetClass:
    """Test cases for get_class function."""

    def test_get_class_success(self):
        """Test successful retrieval of a class."""
        # Test with a simple class from a standard library
        result = get_class("datetime.datetime")
        assert result.__name__ == "datetime"

    def test_get_class_invalid_format(self):
        """Test class retrieval with invalid target format."""
        with pytest.raises(ValueError):
            get_class("invalid_format")

    def test_get_class_invalid_module(self):
        """Test class retrieval with invalid module path."""
        with pytest.raises(ImportError):
            get_class("nonexistent.module.Class")

    def test_get_class_invalid_class(self):
        """Test class retrieval with invalid class name."""
        with pytest.raises(AttributeError):
            get_class("datetime.NonexistentClass")

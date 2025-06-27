"""Unit tests for mindtrace.core.utils.lambdas module."""
# ruff: noqa: E731
# assigning lambdas to variables is useful in this test file and this test file only
from types import FunctionType
from typing import Callable

import pytest

from mindtrace.core.utils.lambdas import named_lambda


class TestNamedLambda:
    """Test suite for the named_lambda function."""

    def test_named_lambda_basic_functionality(self):
        """Test basic functionality of named_lambda with a simple lambda."""
        # Create a lambda function
        original_lambda = lambda x: x * 2
        
        # Apply named_lambda
        named_func = named_lambda("multiply_by_two", original_lambda)
        
        # Test that the name was set correctly
        assert named_func.__name__ == "multiply_by_two"
        
        # Test that the function still works correctly
        assert named_func(5) == 10
        assert named_func(0) == 0
        assert named_func(-3) == -6

    def test_named_lambda_returns_same_object(self):
        """Test that named_lambda returns the same function object."""
        original_lambda = lambda x: x + 1
        named_func = named_lambda("increment", original_lambda)
        
        # Should return the same object, just with modified __name__
        assert named_func is original_lambda

    def test_named_lambda_with_multiple_parameters(self):
        """Test named_lambda with lambda that takes multiple parameters."""
        add_lambda = lambda x, y: x + y
        named_add = named_lambda("add_two_numbers", add_lambda)
        
        assert named_add.__name__ == "add_two_numbers"
        assert named_add(3, 4) == 7
        assert named_add(-1, 1) == 0

    def test_named_lambda_with_keyword_arguments(self):
        """Test named_lambda with lambda that uses keyword arguments."""
        greet_lambda = lambda name, greeting="Hello": f"{greeting}, {name}!"
        named_greet = named_lambda("greet_person", greet_lambda)
        
        assert named_greet.__name__ == "greet_person"
        assert named_greet("Alice") == "Hello, Alice!"
        assert named_greet("Bob", greeting="Hi") == "Hi, Bob!"

    def test_named_lambda_with_complex_logic(self):
        """Test named_lambda with more complex lambda logic."""
        # Lambda with conditional logic
        abs_lambda = lambda x: x if x >= 0 else -x
        named_abs = named_lambda("absolute_value", abs_lambda)
        
        assert named_abs.__name__ == "absolute_value"
        assert named_abs(5) == 5
        assert named_abs(-5) == 5
        assert named_abs(0) == 0

    def test_named_lambda_with_empty_name(self):
        """Test named_lambda with empty string name."""
        test_lambda = lambda x: x
        named_func = named_lambda("", test_lambda)
        
        assert named_func.__name__ == ""
        assert named_func(42) == 42

    def test_named_lambda_with_special_characters_in_name(self):
        """Test named_lambda with special characters in name."""
        test_lambda = lambda x: x
        special_name = "test_function_123!@#"
        named_func = named_lambda(special_name, test_lambda)
        
        assert named_func.__name__ == special_name
        assert named_func("test") == "test"

    def test_named_lambda_preserves_original_behavior(self):
        """Test that named_lambda preserves all original function behavior."""
        # Lambda that returns a complex data structure
        data_lambda = lambda: {"key": "value", "numbers": [1, 2, 3]}
        named_data = named_lambda("create_data", data_lambda)
        
        assert named_data.__name__ == "create_data"
        result = named_data()
        assert result == {"key": "value", "numbers": [1, 2, 3]}
        assert isinstance(result, dict)

    def test_named_lambda_with_regular_function(self):
        """Test named_lambda works with regular functions, not just lambdas."""
        def regular_function(x):
            return x ** 2
        
        original_name = regular_function.__name__
        assert original_name == "regular_function"
        
        renamed_func = named_lambda("square_number", regular_function)
        
        assert renamed_func.__name__ == "square_number"
        assert renamed_func(4) == 16
        assert renamed_func is regular_function  # Same object

    def test_named_lambda_with_builtin_function_raises_error(self):
        """Test named_lambda raises error with built-in functions (read-only __name__)."""
        # Built-in functions have read-only __name__ attributes
        with pytest.raises(AttributeError, match="attribute '__name__' of 'builtin_function_or_method' objects is not writable"):
            named_lambda("get_length", len)

    def test_named_lambda_with_method_raises_error(self):
        """Test named_lambda with instance methods raises error (no __name__ attribute)."""
        class TestClass:
            def __init__(self, value):
                self.value = value
            
            def get_value(self):
                return self.value
        
        obj = TestClass(42)
        # Bound methods don't have a __name__ attribute
        with pytest.raises(AttributeError, match="'method' object has no attribute '__name__'"):
            named_lambda("retrieve_value", obj.get_value)

    def test_named_lambda_type_preservation(self):
        """Test that named_lambda preserves the function type."""
        original_lambda = lambda x: x
        named_func = named_lambda("identity", original_lambda)
        
        assert isinstance(named_func, FunctionType)
        assert callable(named_func)

    def test_named_lambda_with_none_function_raises_error(self):
        """Test that named_lambda raises appropriate error when function is None."""
        with pytest.raises(AttributeError):
            named_lambda("test_name", None)

    def test_named_lambda_name_overwrite(self):
        """Test that named_lambda can overwrite existing function names."""
        def existing_function():
            return "original"
        
        assert existing_function.__name__ == "existing_function"
        
        # Rename the function
        renamed_func = named_lambda("new_function_name", existing_function)
        
        assert renamed_func.__name__ == "new_function_name"
        assert renamed_func() == "original"
        
        # Original function's name is also changed (same object)
        assert existing_function.__name__ == "new_function_name"

    def test_named_lambda_with_closure(self):
        """Test named_lambda with lambda that uses closure variables."""
        multiplier = 3
        multiply_lambda = lambda x: x * multiplier
        named_multiply = named_lambda("triple", multiply_lambda)
        
        assert named_multiply.__name__ == "triple"
        assert named_multiply(4) == 12
        
        # Test that closure still works after renaming
        # Note: In this case, changing the outer variable doesn't affect the lambda
        # because the lambda captures the variable by reference at the time it's called
        multiplier = 5  # This WILL affect the lambda since it captures by reference
        assert named_multiply(4) == 20  # Now uses the updated multiplier value

    def test_named_lambda_docstring_preservation(self):
        """Test that named_lambda preserves function docstrings."""
        def documented_function(x):
            """This function doubles its input."""
            return x * 2
        
        renamed_func = named_lambda("doubler", documented_function)
        
        assert renamed_func.__name__ == "doubler"
        assert renamed_func.__doc__ == "This function doubles its input."
        assert renamed_func(5) == 10

    def test_named_lambda_multiple_calls_same_function(self):
        """Test calling named_lambda multiple times on the same function."""
        original_lambda = lambda x: x + 1
        
        # First renaming
        first_rename = named_lambda("increment", original_lambda)
        assert first_rename.__name__ == "increment"
        
        # Second renaming (should overwrite the name)
        second_rename = named_lambda("add_one", first_rename)
        assert second_rename.__name__ == "add_one"
        
        # All references point to the same object
        assert first_rename is second_rename is original_lambda
        assert original_lambda.__name__ == "add_one"

    def test_named_lambda_with_exception_raising_function(self):
        """Test named_lambda with functions that raise exceptions."""
        error_lambda = lambda: 1 / 0
        named_error = named_lambda("divide_by_zero", error_lambda)
        
        assert named_error.__name__ == "divide_by_zero"
        
        with pytest.raises(ZeroDivisionError):
            named_error()

    def test_named_lambda_integration_example(self):
        """Test integration example similar to the docstring example."""
        # Simulate the example from the docstring
        def run_command(command: Callable, data):
            """Simulate a function that needs the command name."""
            result = command(*data) if isinstance(data, tuple) else command(data)
            return f"Executed '{command.__name__}' with result: {result}"
        
        # Test with unnamed lambda
        unnamed_lambda = lambda x, y: x + y
        result1 = run_command(unnamed_lambda, (3, 4))
        assert "Executed '<lambda>'" in result1
        assert "result: 7" in result1
        
        # Test with named lambda
        named_add = named_lambda("add", lambda x, y: x + y)
        result2 = run_command(named_add, (3, 4))
        assert "Executed 'add'" in result2
        assert "result: 7" in result2

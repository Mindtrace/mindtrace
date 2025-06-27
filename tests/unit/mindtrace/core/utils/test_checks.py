"""Unit test methods for mindtrace.core.utils.checks utility module."""

from unittest.mock import patch

from urllib3.util.url import parse_url

from mindtrace.core import check_libs, ifnone
from mindtrace.core.utils.checks import ifnone_url


def test_ifnone():
    assert ifnone(val=True, default=False) is True
    assert ifnone(val=None, default=False) is False

    assert ifnone(val=5, default=10) == 5
    assert ifnone(val=None, default=10) == 10


def test_first_not_none():
    from mindtrace.core.utils.checks import first_not_none

    # Returns first non-None value
    assert first_not_none([None, None, 3, 4]) == 3
    assert first_not_none([None, "a", None]) == "a"
    assert first_not_none([0, None, 1]) == 0  # 0 is not None

    # All values are None, should return default
    assert first_not_none([None, None], default="fallback") == "fallback"
    assert first_not_none([], default=42) == 42

    # No default provided, should return None if all are None
    assert first_not_none([None, None]) is None
    assert first_not_none([]) is None


def test_check_libs():
    # Test when all libraries are available
    with patch('builtins.__import__') as mock_import:
        mock_import.return_value = None
        assert check_libs(['numpy', 'pandas']) == []

    # Test when some libraries are missing
    with patch('builtins.__import__') as mock_import:
        def mock_import_side_effect(name, *args, **kwargs):
            if name == 'numpy':
                return None
            raise ImportError(f"No module named '{name}'")
        
        mock_import.side_effect = mock_import_side_effect
        assert check_libs(['numpy', 'missing_lib']) == ['missing_lib']

    # Test when all libraries are missing
    with patch('builtins.__import__') as mock_import:
        mock_import.side_effect = ImportError("No module named 'missing_lib'")
        assert check_libs(['missing_lib1', 'missing_lib2']) == ['missing_lib1', 'missing_lib2']


def test_ifnone_url():
    """Test ifnone_url function with various URL inputs."""
    # Test with string URL and string default
    result = ifnone_url("http://example.com", "http://default.com")
    assert str(result) == "http://example.com"
    assert result.host == "example.com"
    
    # Test with None URL and string default
    result = ifnone_url(None, "http://default.com")
    assert str(result) == "http://default.com"
    assert result.host == "default.com"
    
    # Test with string URL and Url object default
    default_url = parse_url("http://default.com")
    result = ifnone_url("http://example.com", default_url)
    assert str(result) == "http://example.com"
    assert result.host == "example.com"
    
    # Test with None URL and Url object default
    default_url = parse_url("http://default.com")
    result = ifnone_url(None, default_url)
    assert str(result) == "http://default.com"
    assert result.host == "default.com"
    assert result is default_url  # Should return the same object
    
    # Test with Url object URL and string default
    url = parse_url("http://example.com")
    result = ifnone_url(url, "http://default.com")
    assert str(result) == "http://example.com"
    assert result.host == "example.com"
    assert result is url  # Should return the same object
    
    # Test with Url object URL and Url object default
    url = parse_url("http://example.com")
    default_url = parse_url("http://default.com")
    result = ifnone_url(url, default_url)
    assert str(result) == "http://example.com"
    assert result.host == "example.com"
    assert result is url  # Should return the same object
    
    # Test with None URL and None default (edge case)
    result = ifnone_url(None, None)
    assert result is None

"""Unit tests for Inspectra core validation."""

import pytest

from mindtrace.apps.inspectra.core.validation import validate_no_whitespace


def test_validate_no_whitespace_none_returns_none():
    assert validate_no_whitespace(None) is None


def test_validate_no_whitespace_empty_returns_empty():
    assert validate_no_whitespace("") == ""


def test_validate_no_whitespace_valid_returns_value():
    assert validate_no_whitespace("Acme") == "Acme"
    assert validate_no_whitespace("Acme-Corp") == "Acme-Corp"


def test_validate_no_whitespace_space_raises():
    with pytest.raises(ValueError, match="cannot contain spaces"):
        validate_no_whitespace("Acme Corp")


def test_validate_no_whitespace_tab_raises():
    with pytest.raises(ValueError, match="cannot contain spaces"):
        validate_no_whitespace("Acme\tCorp")


def test_validate_no_whitespace_custom_message():
    with pytest.raises(ValueError, match="No spaces allowed"):
        validate_no_whitespace("a b", message="No spaces allowed")

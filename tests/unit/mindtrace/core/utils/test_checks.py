"""Unit test methods for mindtrace.core.utils.checks utility module."""

from mindtrace.core import ifnone


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

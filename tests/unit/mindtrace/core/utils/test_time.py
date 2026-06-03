"""Tests for mindtrace.core.utils.time module."""

from datetime import datetime, timedelta, timezone

from mindtrace.core.utils.time import as_utc, utcnow, utcnow_iso


class TestUtcnow:
    """Tests for utcnow function."""

    def test_utcnow_is_timezone_aware_utc(self):
        """utcnow returns a timezone-aware datetime in UTC."""
        now = utcnow()
        assert now.tzinfo is not None
        assert now.utcoffset() == timedelta(0)


class TestUtcnowIso:
    """Tests for utcnow_iso function."""

    def test_utcnow_iso_ends_with_z(self):
        """utcnow_iso returns an ISO-8601 string with a trailing Z (not +00:00)."""
        stamp = utcnow_iso()
        assert stamp.endswith("Z")
        assert "+00:00" not in stamp


class TestAsUtc:
    """Tests for as_utc function."""

    def test_as_utc_treats_naive_as_utc(self):
        """A naive datetime is tagged as UTC without shifting the wall-clock value."""
        naive = datetime(2026, 1, 1, 12, 0, 0)

        result = as_utc(naive)

        assert result.tzinfo is timezone.utc
        assert result == datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    def test_as_utc_converts_aware_to_utc(self):
        """An aware datetime in another zone is converted to the equivalent UTC instant."""
        eastern = timezone(timedelta(hours=-5))
        aware = datetime(2026, 1, 1, 7, 0, 0, tzinfo=eastern)

        result = as_utc(aware)

        assert result.utcoffset() == timedelta(0)
        assert result == datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

# tests/unit/mindtrace/storage/test_base.py
"""Unit tests for base storage types and operations."""

from mindtrace.storage.base import BatchResult, FileResult, Status, StringResult

# ---------------------------------------------------------------------------
# Status Enum Tests
# ---------------------------------------------------------------------------


class TestStatus:
    def test_status_string_comparison(self):
        """Test Status enum can be compared as strings."""
        assert Status.OK == "ok"
        assert Status.ERROR == "error"
        assert Status.NOT_FOUND == "not_found"
        assert Status.SKIPPED == "skipped"
        assert Status.ALREADY_EXISTS == "already_exists"
        assert Status.OVERWRITTEN == "overwritten"

    def test_status_inequality(self):
        """Test Status enum inequality."""
        assert Status.OK != "error"
        assert Status.OK != Status.ERROR

    def test_status_values(self):
        """Test Status enum values are correct strings."""
        assert Status.OK.value == "ok"
        assert Status.ERROR.value == "error"
        assert Status.NOT_FOUND.value == "not_found"
        assert Status.SKIPPED.value == "skipped"
        assert Status.ALREADY_EXISTS.value == "already_exists"
        assert Status.OVERWRITTEN.value == "overwritten"


# ---------------------------------------------------------------------------
# FileResult Tests
# ---------------------------------------------------------------------------


class TestFileResult:
    def test_ok_property_ok_status(self):
        """Test ok property returns True for OK status."""
        result = FileResult(local_path="local.txt", remote_path="remote.txt", status=Status.OK)
        assert result.ok is True

    def test_ok_property_overwritten_status(self):
        """Test ok property returns True for OVERWRITTEN status."""
        result = FileResult(local_path="local.txt", remote_path="remote.txt", status=Status.OVERWRITTEN)
        assert result.ok is True

    def test_ok_property_skipped_status(self):
        """Test ok property returns True for SKIPPED status."""
        result = FileResult(local_path="local.txt", remote_path="remote.txt", status=Status.SKIPPED)
        assert result.ok is True

    def test_ok_property_error_status(self):
        """Test ok property returns False for ERROR status."""
        result = FileResult(local_path="local.txt", remote_path="remote.txt", status=Status.ERROR)
        assert result.ok is False

    def test_ok_property_not_found_status(self):
        """Test ok property returns False for NOT_FOUND status."""
        result = FileResult(local_path="local.txt", remote_path="remote.txt", status=Status.NOT_FOUND)
        assert result.ok is False

    def test_ok_property_already_exists_status(self):
        """Test ok property returns False for ALREADY_EXISTS status."""
        result = FileResult(local_path="local.txt", remote_path="remote.txt", status=Status.ALREADY_EXISTS)
        assert result.ok is False

    def test_file_result_with_error_fields(self):
        """Test FileResult with error fields populated."""
        result = FileResult(
            local_path="local.txt",
            remote_path="remote.txt",
            status=Status.ERROR,
            error_type="NetworkError",
            error_message="Connection refused",
        )
        assert result.status == Status.ERROR
        assert result.error_type == "NetworkError"
        assert result.error_message == "Connection refused"
        assert result.ok is False

    def test_file_result_default_error_fields(self):
        """Test FileResult has None as default for error fields."""
        result = FileResult(local_path="local.txt", remote_path="remote.txt", status=Status.OK)
        assert result.error_type is None
        assert result.error_message is None


# ---------------------------------------------------------------------------
# StringResult Tests
# ---------------------------------------------------------------------------


class TestStringResult:
    def test_ok_property_ok_status(self):
        """Test ok property returns True for OK status."""
        result = StringResult(remote_path="remote.txt", status=Status.OK)
        assert result.ok is True

    def test_ok_property_overwritten_status(self):
        """Test ok property returns True for OVERWRITTEN status."""
        result = StringResult(remote_path="remote.txt", status=Status.OVERWRITTEN)
        assert result.ok is True

    def test_ok_property_skipped_status(self):
        """Test ok property returns True for SKIPPED status."""
        result = StringResult(remote_path="remote.txt", status=Status.SKIPPED)
        assert result.ok is True

    def test_ok_property_error_status(self):
        """Test ok property returns False for ERROR status."""
        result = StringResult(remote_path="remote.txt", status=Status.ERROR)
        assert result.ok is False

    def test_ok_property_not_found_status(self):
        """Test ok property returns False for NOT_FOUND status."""
        result = StringResult(remote_path="remote.txt", status=Status.NOT_FOUND)
        assert result.ok is False

    def test_ok_property_already_exists_status(self):
        """Test ok property returns False for ALREADY_EXISTS status."""
        result = StringResult(remote_path="remote.txt", status=Status.ALREADY_EXISTS)
        assert result.ok is False

    def test_string_result_with_content(self):
        """Test StringResult with content populated."""
        result = StringResult(
            remote_path="remote.txt",
            status=Status.OK,
            content=b"file content",
        )
        assert result.content == b"file content"

    def test_string_result_default_content(self):
        """Test StringResult has None as default for content."""
        result = StringResult(remote_path="remote.txt", status=Status.OK)
        assert result.content is None

    def test_string_result_with_error_fields(self):
        """Test StringResult with error fields populated."""
        result = StringResult(
            remote_path="remote.txt",
            status=Status.ERROR,
            error_type="NotFound",
            error_message="Object not found",
        )
        assert result.error_type == "NotFound"
        assert result.error_message == "Object not found"


# ---------------------------------------------------------------------------
# BatchResult Tests
# ---------------------------------------------------------------------------


class TestBatchResult:
    def test_iter(self):
        """Test BatchResult is iterable."""
        results = [
            FileResult(local_path="a", remote_path="a", status=Status.OK),
            FileResult(local_path="b", remote_path="b", status=Status.ERROR),
        ]
        batch = BatchResult(results=results)
        assert list(batch) == results

    def test_len(self):
        """Test BatchResult has correct length."""
        results = [
            FileResult(local_path="a", remote_path="a", status=Status.OK),
            FileResult(local_path="b", remote_path="b", status=Status.OK),
        ]
        batch = BatchResult(results=results)
        assert len(batch) == 2

    def test_len_empty(self):
        """Test BatchResult length is 0 for empty results."""
        batch = BatchResult(results=[])
        assert len(batch) == 0

    def test_ok_results_filters_successful(self):
        """Test ok_results returns only successful operations."""
        results = [
            FileResult(local_path="a", remote_path="a", status=Status.OK),
            FileResult(local_path="b", remote_path="b", status=Status.ERROR),
            FileResult(local_path="c", remote_path="c", status=Status.SKIPPED),
            FileResult(local_path="d", remote_path="d", status=Status.OVERWRITTEN),
        ]
        batch = BatchResult(results=results)
        ok = batch.ok_results
        assert len(ok) == 3  # OK, SKIPPED, OVERWRITTEN
        assert all(r.ok for r in ok)

    def test_ok_results_excludes_failures(self):
        """Test ok_results excludes ERROR, NOT_FOUND, ALREADY_EXISTS."""
        results = [
            FileResult(local_path="a", remote_path="a", status=Status.ERROR),
            FileResult(local_path="b", remote_path="b", status=Status.NOT_FOUND),
            FileResult(local_path="c", remote_path="c", status=Status.ALREADY_EXISTS),
        ]
        batch = BatchResult(results=results)
        assert len(batch.ok_results) == 0

    def test_skipped_results(self):
        """Test skipped_results returns SKIPPED and ALREADY_EXISTS."""
        results = [
            FileResult(local_path="a", remote_path="a", status=Status.OK),
            FileResult(local_path="b", remote_path="b", status=Status.SKIPPED),
            FileResult(local_path="c", remote_path="c", status=Status.ALREADY_EXISTS),
            FileResult(local_path="d", remote_path="d", status=Status.ERROR),
        ]
        batch = BatchResult(results=results)
        skipped = batch.skipped_results
        assert len(skipped) == 2
        statuses = {r.status for r in skipped}
        assert Status.SKIPPED in statuses
        assert Status.ALREADY_EXISTS in statuses

    def test_conflict_results(self):
        """Test conflict_results returns only ALREADY_EXISTS."""
        results = [
            FileResult(local_path="a", remote_path="a", status=Status.OK),
            FileResult(local_path="b", remote_path="b", status=Status.SKIPPED),
            FileResult(local_path="c", remote_path="c", status=Status.ALREADY_EXISTS),
            FileResult(local_path="d", remote_path="d", status=Status.ALREADY_EXISTS),
        ]
        batch = BatchResult(results=results)
        conflicts = batch.conflict_results
        assert len(conflicts) == 2
        assert all(r.status == Status.ALREADY_EXISTS for r in conflicts)

    def test_failed_results(self):
        """Test failed_results returns NOT_FOUND and ERROR."""
        results = [
            FileResult(local_path="a", remote_path="a", status=Status.OK),
            FileResult(local_path="b", remote_path="b", status=Status.NOT_FOUND),
            FileResult(local_path="c", remote_path="c", status=Status.ERROR),
            FileResult(local_path="d", remote_path="d", status=Status.ALREADY_EXISTS),
        ]
        batch = BatchResult(results=results)
        failed = batch.failed_results
        assert len(failed) == 2
        statuses = {r.status for r in failed}
        assert Status.NOT_FOUND in statuses
        assert Status.ERROR in statuses

    def test_all_ok_true_when_all_ok(self):
        """Test all_ok returns True when all results have OK status."""
        results = [
            FileResult(local_path="a", remote_path="a", status=Status.OK),
            FileResult(local_path="b", remote_path="b", status=Status.OK),
        ]
        batch = BatchResult(results=results)
        assert batch.all_ok is True

    def test_all_ok_false_with_error(self):
        """Test all_ok returns False when any result has ERROR status."""
        results = [
            FileResult(local_path="a", remote_path="a", status=Status.OK),
            FileResult(local_path="b", remote_path="b", status=Status.ERROR),
        ]
        batch = BatchResult(results=results)
        assert batch.all_ok is False

    def test_all_ok_false_with_skipped(self):
        """Test all_ok returns False when any result has SKIPPED status.

        Note: all_ok checks for Status.OK specifically, not .ok property.
        """
        results = [
            FileResult(local_path="a", remote_path="a", status=Status.OK),
            FileResult(local_path="b", remote_path="b", status=Status.SKIPPED),
        ]
        batch = BatchResult(results=results)
        assert batch.all_ok is False

    def test_all_ok_false_with_overwritten(self):
        """Test all_ok returns False when any result has OVERWRITTEN status."""
        results = [
            FileResult(local_path="a", remote_path="a", status=Status.OK),
            FileResult(local_path="b", remote_path="b", status=Status.OVERWRITTEN),
        ]
        batch = BatchResult(results=results)
        assert batch.all_ok is False

    def test_all_ok_true_empty_batch(self):
        """Test all_ok returns True for empty batch (vacuously true)."""
        batch = BatchResult(results=[])
        assert batch.all_ok is True

    def test_empty_batch_properties(self):
        """Test all properties work correctly on empty batch."""
        batch = BatchResult(results=[])
        assert len(batch) == 0
        assert len(batch.ok_results) == 0
        assert len(batch.skipped_results) == 0
        assert len(batch.conflict_results) == 0
        assert len(batch.failed_results) == 0
        assert batch.all_ok is True

    def test_single_result_batch(self):
        """Test batch with single result."""
        results = [FileResult(local_path="a", remote_path="a", status=Status.OK)]
        batch = BatchResult(results=results)
        assert len(batch) == 1
        assert len(batch.ok_results) == 1
        assert batch.all_ok is True

    def test_all_statuses_batch(self):
        """Test batch with all possible statuses."""
        results = [
            FileResult(local_path="a", remote_path="a", status=Status.OK),
            FileResult(local_path="b", remote_path="b", status=Status.SKIPPED),
            FileResult(local_path="c", remote_path="c", status=Status.ALREADY_EXISTS),
            FileResult(local_path="d", remote_path="d", status=Status.OVERWRITTEN),
            FileResult(local_path="e", remote_path="e", status=Status.NOT_FOUND),
            FileResult(local_path="f", remote_path="f", status=Status.ERROR),
        ]
        batch = BatchResult(results=results)

        assert len(batch) == 6
        assert len(batch.ok_results) == 3  # OK, SKIPPED, OVERWRITTEN
        assert len(batch.skipped_results) == 2  # SKIPPED, ALREADY_EXISTS
        assert len(batch.conflict_results) == 1  # ALREADY_EXISTS
        assert len(batch.failed_results) == 2  # NOT_FOUND, ERROR
        assert batch.all_ok is False

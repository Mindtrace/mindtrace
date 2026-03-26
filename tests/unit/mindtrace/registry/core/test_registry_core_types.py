from mindtrace.registry.core.types import CleanupState, OpResult, OpResults


def test_cleanup_state_properties():
    assert CleanupState.ORPHANED.has_orphan is True
    assert CleanupState.OK.has_orphan is False
    assert CleanupState.UNKNOWN.has_unknown is True
    assert CleanupState.OK.has_unknown is False


def test_opresult_failed_explicit_error_and_to_dict_cleanup():
    result = OpResult.failed("artifact", "1.0", error_type="Custom", message="boom", cleanup=CleanupState.UNKNOWN)
    as_dict = result.to_dict()

    assert result.ok is False
    assert as_dict == {"status": "error", "error": "Custom", "message": "boom", "cleanup": "unknown"}


def test_opresults_raise_on_errors_aggregates_messages():
    results = OpResults()
    results.add(OpResult.success("a", "1"))
    results.add(OpResult.failed("b", "2", ValueError("invalid")))

    try:
        results.raise_on_errors("Batch failed")
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        message = str(exc)
        assert "Batch failed" in message
        assert "b@2: ValueError - invalid" in message

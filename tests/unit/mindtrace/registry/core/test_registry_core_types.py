import pytest

from mindtrace.registry.core.types import BatchResult, CleanupState, OpResult, OpResults, Version


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


def test_version_validation_edge_cases():
    with pytest.raises(ValueError, match="digits must be >= 1"):
        Version("1", digits=0)

    with pytest.raises(ValueError, match="Version cannot be None"):
        Version._parse(None, digits=3)

    with pytest.raises(ValueError, match="Version cannot be empty"):
        Version("   ", digits=3)

    with pytest.raises(ValueError, match="Expected numeric components"):
        Version("1.a", digits=3)

    with pytest.raises(ValueError, match="non-negative integers"):
        Version("-1", digits=3)

    version = Version("v2.3", digits=3)
    assert version.parts == (2, 3, 0)
    assert version.normalized == "2.3.0"


def test_opresult_success_variants_and_properties():
    skipped = OpResult.skipped("artifact", "1.0", cleanup=CleanupState.OK)
    overwritten = OpResult.overwritten("artifact", "2.0", cleanup=CleanupState.ORPHANED)
    success = OpResult.success(
        "artifact",
        "3.0",
        metadata={"size": 1},
        path="/tmp/artifact",
        cleanup=CleanupState.UNKNOWN,
        status="ok",
    )

    assert skipped.is_skipped is True
    assert skipped.to_dict() == {"status": "skipped", "cleanup": "ok"}

    assert overwritten.is_overwritten is True
    assert overwritten.to_dict() == {"status": "overwritten", "cleanup": "orphaned"}

    assert success.key == ("artifact", "3.0")
    assert success.to_dict() == {
        "status": "ok",
        "metadata": {"size": 1},
        "path": "/tmp/artifact",
        "cleanup": "unknown",
    }


def test_opresults_collection_helpers_and_dict_conversion():
    success = OpResult.success("a", "1", metadata={"x": 1}, path="/tmp/a")
    failure = OpResult.failed("b", "2", RuntimeError("boom"))
    skipped = OpResult.skipped("c", "3")

    results = OpResults()
    assert results.first() is None

    results.add(success)
    results.add(failure)
    results.add(skipped)

    assert results[("a", "1")] is success
    assert ("b", "2") in results
    assert results.get(("missing", "0")) is None
    assert list(results.keys()) == [("a", "1"), ("b", "2"), ("c", "3")]
    assert list(results.values()) == [success, failure, skipped]
    assert list(results.items()) == [
        (("a", "1"), success),
        (("b", "2"), failure),
        (("c", "3"), skipped),
    ]
    assert list(results) == [success, failure, skipped]
    assert len(results) == 3
    assert bool(results) is True
    assert results.successful == [success, skipped]
    assert results.failed == [failure]
    assert results.errors == [failure]
    assert results.all_ok is False
    assert results.any_failed is True
    assert results.to_dict() == {
        ("a", "1"): {"status": "ok", "metadata": {"x": 1}, "path": "/tmp/a"},
        ("b", "2"): {"status": "error", "error": "RuntimeError", "message": "boom"},
        ("c", "3"): {"status": "skipped"},
    }


def test_batch_result_helpers():
    result = BatchResult(
        results=["ok", None, "skipped"],
        errors={("b", "2"): {"error": "RuntimeError", "message": "boom"}},
        succeeded=[("a", "1")],
        skipped=[("c", "3")],
        failed=[("b", "2")],
        cleanup_needed={("a", "1"): CleanupState.ORPHANED},
    )

    assert len(result) == 3
    assert result[0] == "ok"
    assert list(result) == ["ok", None, "skipped"]
    assert result.all_succeeded is False
    assert result.success_count == 1
    assert result.skipped_count == 1
    assert result.failure_count == 1
    assert result.cleanup_required_count == 1

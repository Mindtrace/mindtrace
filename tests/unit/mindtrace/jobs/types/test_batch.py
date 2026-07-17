from mindtrace.jobs import BatchPublishResult


def test_batch_publish_result_tracks_success_failure_and_unattempted_items():
    result = BatchPublishResult(
        job_ids=["job-1", None, None],
        errors={1: {"error": "RuntimeError", "message": "publish failed"}},
    )

    assert result.successful_indices == [0]
    assert result.failed_indices == [1]
    assert result.unattempted_indices == [2]
    assert result.success_count == 1
    assert result.failure_count == 1
    assert result.unattempted_count == 1
    assert result.all_succeeded is False


def test_empty_batch_publish_result_succeeds():
    result = BatchPublishResult.for_batch_size(0)

    assert result.job_ids == []
    assert result.all_succeeded is True


def test_setup_failure_leaves_all_items_unattempted():
    result = BatchPublishResult.for_batch_size(2)
    result.setup_error = {"error": "ConnectionError", "message": "broker unavailable"}

    assert result.failed_indices == []
    assert result.unattempted_indices == [0, 1]
    assert result.failure_count == 1
    assert result.all_succeeded is False

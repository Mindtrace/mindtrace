import time

import pytest


def wait_for_job_status(cluster_cm, job_id, expected_status, timeout=10, poll_interval=0.1):
    """Poll job status until it matches expected_status or timeout."""
    start = time.time()
    result = None
    while time.time() - start < timeout:
        result = cluster_cm.get_job_status(job_id=job_id)
        if result.status == expected_status:
            return result
        time.sleep(poll_interval)
    pytest.fail(f"Job {job_id} did not reach '{expected_status}' within {timeout}s. Last: {result.status}")

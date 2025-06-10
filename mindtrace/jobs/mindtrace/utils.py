from typing import Any
from .types import JobType, QUEUE_MAPPING, Job


def ifnone(val: Any, default: Any) -> Any:
    """Return default if val is None, otherwise return val."""
    return default if val is None else val


def get_queue_for_job_type(job_type: JobType) -> str:
    """
    Get the appropriate queue name for a given job type.

    Args:
        job_type: The JobType enum value

    Returns:
        Queue name string
    """
    return QUEUE_MAPPING[job_type]


def get_queue_for_job(job: Job) -> str:
    """
    Get the appropriate queue name for a given job.

    Args:
        job: The Job instance

    Returns:
        Queue name string
    """
    return get_queue_for_job_type(job.job_type)

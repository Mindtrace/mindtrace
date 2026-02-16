from pprint import pprint as pp

from mindtrace.cluster.core import types as cluster_types


def process_dlq(cluster_manager):
    """
    A simple function to process the dead letter queue with user input.
    The user can choose to requeue, discard, skip, or quit the program.
    So the intended way to call this is in a simple CLI script:
    ```python
    from mindtrace.cluster.core.dlq import process_dlq
    from mindtrace.cluster import ClusterManager
    cluster_manager = ClusterManager.connect(...)
    requeue_jobs = process_dlq(cluster_manager)
    ```
    Alternatively, if you want to process the DLQ in a more complex or programmatic way,
    you can copy this function and modify it to your needs.

    Args:
        cluster_manager: A ConnectionManager for a ClusterManager service.
    Returns:
        requeue_jobs: list[cluster_types.DLQJobStatus]: The jobs that were requeued.
    """
    jobs = cluster_manager.get_dlq_jobs().jobs
    requeue_jobs: list[cluster_types.DLQJobStatus] = []
    for job in jobs:
        pp(job)
        todo = input("What to do? ([r]equeue/[d]iscard/[s]kip/[q]uit): ")
        if todo == "r":
            requeue_jobs.append(cluster_manager.requeue_from_dlq(job_id=job.job_id))
        elif todo == "d":
            cluster_manager.discard_from_dlq(job_id=job.job_id)
        elif todo == "s":
            continue
        elif todo == "q":
            break
    return requeue_jobs

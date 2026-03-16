import time

from mindtrace.cluster import ClusterManager
from mindtrace.cluster.core.types import JobStatusEnum
from mindtrace.core import get_free_ports
from mindtrace.jobs import JobSchema, job_from_schema
from mindtrace.services.samples.echo_service import EchoInput, EchoOutput


def main():
    """
    Minimal reproduction script for the "two auto-connect workers" bug.

    Expected usage:
    - Start a ClusterManager and Node, e.g. via samples/cluster/separate_node/cluster_and_node.py
      so that:
        cluster_url = "http://localhost:8002"
        node_url = "http://localhost:8003"
    - Then run this script to:
        * register two EchoWorker-based worker types with different job schemas
        * launch two workers simultaneously with auto-connect
        * submit one job to each schema and observe behaviour
    """

    cluster_url = "http://localhost:8502"
    node_url = "http://localhost:8503"

    cluster_cm = ClusterManager.connect(cluster_url)

    # Register two worker types, each with its own job schema for auto-connect
    cluster_cm.register_worker_type(
        worker_name="echoworker1",
        worker_class="mindtrace.cluster.workers.echo_worker.EchoWorker",
        worker_params={},
        job_type="echo1",
    )
    cluster_cm.register_worker_type(
        worker_name="echoworker2",
        worker_class="mindtrace.cluster.workers.echo_worker.EchoWorker",
        worker_params={},
        job_type="echo2",
    )

    # Launch workers for both types on two free ports
    port1, port2 = get_free_ports(ports_to_find=2)
    worker_url1 = f"http://localhost:{port1}"
    worker_url2 = f"http://localhost:{port2}"

    print(f"Launching echoworker1 at {worker_url1}")
    launch1 = cluster_cm.launch_worker(
        node_url=node_url,
        worker_type="echoworker1",
        worker_url=worker_url1,
    )

    print(f"Launching echoworker2 at {worker_url2}")
    launch2 = cluster_cm.launch_worker(
        node_url=node_url,
        worker_type="echoworker2",
        worker_url=worker_url2,
    )

    print(f"Launch IDs: {launch1.launch_id}, {launch2.launch_id}")

    # Simple polling loop for launch status (mirrors tests' wait_for_worker_launch helper)
    def wait_for_worker(launch, label: str, timeout: float = 60.0, poll_interval: float = 0.5):
        from mindtrace.cluster.core.types import LaunchStatusEnum

        start = time.time()
        last = None
        while time.time() - start < timeout:
            status = cluster_cm.launch_worker_status(node_url=node_url, launch_id=launch.launch_id)
            last = status
            print(f"{label} status: {status.status} (id={status.launch_id}, url={status.worker_url})")
            if status.status in (LaunchStatusEnum.READY, LaunchStatusEnum.FAILED):
                return status
            time.sleep(poll_interval)
        raise RuntimeError(f"{label} did not become READY within {timeout}s; last={getattr(last, 'status', None)}")

    status1 = wait_for_worker(launch1, "worker1")
    status2 = wait_for_worker(launch2, "worker2")

    print(f"Final worker1 status: {status1}")
    print(f"Final worker2 status: {status2}")

    # Submit one job to each schema
    echo_job_schema1 = JobSchema(name="echo1", input_schema=EchoInput, output_schema=EchoOutput)
    echo_job_schema2 = JobSchema(name="echo2", input_schema=EchoInput, output_schema=EchoOutput)

    job1 = job_from_schema(echo_job_schema1, input_data={"message": "Worker 1 job!"})
    job2 = job_from_schema(echo_job_schema2, input_data={"message": "Worker 2 job!"})

    print("Submitting jobs...")
    result1 = cluster_cm.submit_job(job1)
    result2 = cluster_cm.submit_job(job2)
    print(f"Initial job1 status: {result1}")
    print(f"Initial job2 status: {result2}")

    # Poll job status a few times to observe whether they leave the queued state
    for i in range(10):
        time.sleep(1.0)
        s1 = cluster_cm.get_job_status(job_id=job1.id)
        s2 = cluster_cm.get_job_status(job_id=job2.id)
        print(f"[t+{i + 1:02d}s] job1: {s1.status}, output={s1.output}")
        print(f"[t+{i + 1:02d}s] job2: {s2.status}, output={s2.output}")
        if s1.status == JobStatusEnum.COMPLETED and s2.status == JobStatusEnum.COMPLETED:
            break


if __name__ == "__main__":
    main()

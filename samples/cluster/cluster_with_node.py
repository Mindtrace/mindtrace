import time

from mindtrace.services.sample.echo_service import EchoInput, EchoOutput

from mindtrace.cluster import ClusterManager, Node
from mindtrace.jobs import JobSchema, job_from_schema


def main():
    cluster_manager = ClusterManager.launch(host="localhost", port=8002, wait_for_launch=True)
    node = Node.launch(
        host="localhost", port=8003, cluster_url=str(cluster_manager.url), wait_for_launch=True, timeout=15
    )
    try:
        cluster_manager.register_worker_type(
            worker_name="echoworker", worker_class="mindtrace.cluster.workers.echo_worker.EchoWorker", worker_params={}
        )
        worker_url = "http://localhost:8004"
        node.launch_worker(worker_type="echoworker", worker_url=worker_url)
        echo_job_schema = JobSchema(name="echo", input=EchoInput, output=EchoOutput)
        cluster_manager.register_job_to_worker(job_type="echo", worker_url=worker_url)
        job = job_from_schema(echo_job_schema, input_data={"message": "Hello, World!", "delay": 3})
        cluster_manager.submit_job(job)
        print(cluster_manager.get_job_status(job_id=job.id))
        time.sleep(1)
        print(cluster_manager.get_job_status(job_id=job.id))
        time.sleep(5)
        print(cluster_manager.get_job_status(job_id=job.id))
    finally:
        node.shutdown()
        cluster_manager.clear_databases()
        cluster_manager.shutdown()


if __name__ == "__main__":
    main()

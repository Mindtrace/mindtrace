import time

from mindtrace.cluster import ClusterManager
from mindtrace.cluster.workers.echo_worker import EchoWorker
from mindtrace.jobs import JobSchema, job_from_schema
from mindtrace.services.sample.echo_service import EchoInput, EchoOutput


def main():
    cluster_manager = ClusterManager.launch(host="localhost", port=8000, wait_for_launch=True)
    worker_cm = EchoWorker.launch(host="localhost", port=8001, wait_for_launch=True)
    try:
        echo_job_schema = JobSchema(name="echo", input=EchoInput, output=EchoOutput)
        cluster_manager.register_job_to_worker(job_type="echo", worker_url=str(worker_cm.url))
        job = job_from_schema(echo_job_schema, input_data={"message": "Hello, World!", "delay": 3})
        cluster_manager.submit_job(job)
        print(cluster_manager.get_job_status(job_id=job.id))
        print(worker_cm.get_status())
        print(cluster_manager.query_worker_status_by_url(worker_url=str(worker_cm.url)))
        time.sleep(1)
        print(cluster_manager.get_job_status(job_id=job.id))
        print(worker_cm.get_status())
        print(cluster_manager.query_worker_status_by_url(worker_url=str(worker_cm.url)))
        time.sleep(5)
        print(cluster_manager.get_job_status(job_id=job.id))
        print(worker_cm.get_status())
        print(cluster_manager.query_worker_status_by_url(worker_url=str(worker_cm.url)))
    finally:
        worker_cm.shutdown()
        cluster_manager.clear_databases()
        cluster_manager.shutdown()


if __name__ == "__main__":
    main()

import time

from mindtrace.cluster import ClusterManager
from mindtrace.cluster.workers.echo_worker import EchoWorker
from mindtrace.jobs import JobSchema, job_from_schema
from mindtrace.services.sample.echo_service import EchoInput, EchoOutput


def main():
    cluster_manager = ClusterManager.connect("http://localhost:8000")
    worker_cm = EchoWorker.connect("http://localhost:8001")
    try:
        echo_job_schema = JobSchema(name="echo", input=EchoInput, output=EchoOutput)
        job = job_from_schema(echo_job_schema, input_data={"message": "Hello, World!", "delay": 60})
        cluster_manager.submit_job(**job.model_dump())
        print(cluster_manager.get_job_status(job_id=job.id))
        time.sleep(1)
        print(cluster_manager.get_job_status(job_id=job.id))
        time.sleep(65)
        print(cluster_manager.get_job_status(job_id=job.id))
    finally:
        worker_cm.shutdown()
        cluster_manager.shutdown()

if __name__ == "__main__":
    main()
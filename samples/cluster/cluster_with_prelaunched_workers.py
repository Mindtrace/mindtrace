from mindtrace.cluster import ClusterManager
from mindtrace.cluster.workers.echo_worker import EchoWorker
from mindtrace.jobs import Job, JobSchema, job_from_schema
from mindtrace.services.sample.echo_service import EchoInput, EchoOutput

def main():
    cluster_manager = ClusterManager.launch(host="localhost", port=8000, wait_for_launch=True)
    worker_cm = EchoWorker.launch(host="localhost", port=8001, wait_for_launch=True)
    echo_job_schema = JobSchema(name="echo", input=EchoInput, output=EchoOutput)
    cluster_manager.register_job_to_worker(job_type="echo", worker_url=str(worker_cm.url))
    job = job_from_schema(echo_job_schema, input_data={"message": "Hello, World!"})
    cluster_manager.submit_job(**job.model_dump())
    worker_cm.shutdown()
    cluster_manager.shutdown()

if __name__ == "__main__":
    main()
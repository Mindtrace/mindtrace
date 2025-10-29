from mindtrace.cluster import ClusterManager
from mindtrace.cluster.workers.echo_worker import EchoWorker
from mindtrace.jobs import JobSchema
from mindtrace.services.samples.echo_service import EchoInput, EchoOutput

if __name__ == "__main__":
    cluster_manager = ClusterManager.connect("http://localhost:8002")
    worker_cm = EchoWorker.connect("http://localhost:8003")
    echo_job_schema = JobSchema(name="echo", input_schema=EchoInput, output_schema=EchoOutput)
    cluster_manager.register_job_to_worker(job_type="echo", worker_url=str(worker_cm.url))

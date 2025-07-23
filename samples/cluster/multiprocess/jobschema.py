from mindtrace.cluster import ClusterManager
from mindtrace.cluster.workers.echo_worker import EchoWorker
from mindtrace.jobs import JobSchema
from mindtrace.services.sample.echo_service import EchoInput, EchoOutput

if __name__ == "__main__":
    cluster_manager = ClusterManager.connect("http://localhost:8000")
    worker_cm = EchoWorker.connect("http://localhost:8001")
    echo_job_schema = JobSchema(name="echo", input=EchoInput, output=EchoOutput)
    cluster_manager.register_job_to_worker(job_type="echo", worker_url=str(worker_cm.url))

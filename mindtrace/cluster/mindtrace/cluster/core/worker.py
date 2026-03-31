import threading
from abc import abstractmethod

from mindtrace.cluster.core import types as cluster_types
from mindtrace.cluster.core.utils import update_database
from mindtrace.core import TaskSchema
from mindtrace.database import BackendType, UnifiedMindtraceODM
from mindtrace.jobs import Consumer
from mindtrace.services import EndpointSpec, Service

# -- Worker endpoint schemas --
_WORKER_SCHEMAS = {
    "start": TaskSchema(name="start_worker"),
    "run": TaskSchema(
        name="run_worker", input_schema=cluster_types.WorkerRunInput, output_schema=cluster_types.JobStatus
    ),
    "connect_to_cluster": TaskSchema(name="connect_to_cluster", input_schema=cluster_types.ConnectToBackendInput),
    "get_status": TaskSchema(name="get_status", output_schema=cluster_types.WorkerStatusLocal),
}


class Worker(Service, Consumer):
    _endpoint_specs = [
        EndpointSpec(path="start", method_name="start", schema=_WORKER_SCHEMAS["start"]),
        EndpointSpec(path="run", method_name="run", schema=_WORKER_SCHEMAS["run"]),
        EndpointSpec(
            path="connect_to_cluster", method_name="connect_to_cluster", schema=_WORKER_SCHEMAS["connect_to_cluster"]
        ),
        EndpointSpec(path="get_status", method_name="get_status", schema=_WORKER_SCHEMAS["get_status"]),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.redis_url = kwargs.get("redis_url", self.config["MINDTRACE_WORKER"]["DEFAULT_REDIS_URL"])
        self.worker_status_local_database = UnifiedMindtraceODM(
            unified_model_cls=cluster_types.WorkerStatusLocal,
            redis_url=self.redis_url,
            preferred_backend=BackendType.REDIS,
        )
        self.worker_status_local_database.initialize_sync()
        self.worker_status_local_database.insert(
            cluster_types.WorkerStatusLocal(
                worker_id=str(self.id),
                status=cluster_types.WorkerStatusEnum.IDLE,
                job_id=None,
            )
        )
        self.consume_thread = None
        self._cluster_connection_manager = None  # type: ignore
        self._cluster_url = None

    @property
    def cluster_connection_manager(self):
        if self._cluster_connection_manager is None and self._cluster_url is not None:
            from mindtrace.cluster.core.cluster_manager import ClusterManager

            self._cluster_connection_manager = ClusterManager.connect(self._cluster_url)
        return self._cluster_connection_manager

    def run(self, job_dict: dict):
        """
        Run a job. Alerts the cluster manager that the job has started and completed; in between it calls self._run().

        Args:
            job_dict (dict): The job dictionary.

        Returns:
            dict: The output of the job.
        """
        cm = self.cluster_connection_manager
        if cm:
            cm.worker_alert_started_job(job_id=job_dict["id"], worker_id=str(self.id))
        else:
            self.logger.warning(f"No cluster connection manager found for worker {self.id}")

        update_database(
            self.worker_status_local_database,
            "worker_id",
            str(self.id),
            {"status": cluster_types.WorkerStatusEnum.RUNNING, "job_id": job_dict["id"]},
        )
        try:
            output = self._run(job_dict["payload"])
        except Exception as e:
            output = {"status": cluster_types.JobStatusEnum.FAILED, "output": {}}
            self.logger.error(f"Error running job {job_dict['id']}: {e}")
        if cm:
            cm.worker_alert_completed_job(
                job_id=job_dict["id"], worker_id=str(self.id), status=output["status"], output=output["output"]
            )
        else:
            self.logger.warning(f"No cluster connection manager found for worker {self.id}")
        update_database(
            self.worker_status_local_database,
            "worker_id",
            str(self.id),
            {"status": cluster_types.WorkerStatusEnum.IDLE, "job_id": None},
        )
        return output

    @abstractmethod
    def _run(self, job_dict: dict) -> dict:
        """
        The main method that runs the job. Should be implemented by the Worker subclass.

        Args:
            job_dict (dict): The Job object as a dictionary.

        Returns:
            dict: The output of the job.
        """
        raise NotImplementedError("Subclasses must implement this method")  # pragma: no cover

    def start(self):
        """
        Put any initialization code that wants to run after the worker is connected to the cluster here.
        """
        pass

    def connect_to_cluster(self, payload: dict):
        """
        Connect the worker to a Cluster and an Orchestrator.
        This is called by the cluster manager once the worker is launched.

        Args:
            payload (dict): The payload containing the Orchestrator backend arguments,
                queue name to listen on, and cluster URL to report back to.
        """
        backend_args = payload["backend_args"]
        queue_name = payload["queue_name"]
        cluster_url = payload["cluster_url"]

        # Set the cluster URL so the worker can report back
        self._cluster_url = cluster_url

        self.start()
        self.connect_to_orchestator_via_backend_args(backend_args, queue_name=queue_name)
        self.logger.info(f"Worker {self.id} connected to cluster {cluster_url} listening on queue {queue_name}")
        self.consume_thread = threading.Thread(target=self.consume)
        self.consume_thread.start()
        self.logger.info(f"Worker {self.id} started consuming from queue {queue_name}")

    def get_status(self):
        """
        Get the status of the worker.
        """
        return self.worker_status_local_database.find(
            self.worker_status_local_database.redis_backend.model_cls.worker_id == str(self.id)
        )[0]

import urllib.parse
from datetime import datetime

import requests
from pydantic import BaseModel

from mindtrace.cluster.core import types as cluster_types
from mindtrace.cluster.core.utils import update_database
from mindtrace.core import TaskSchema
from mindtrace.database import BackendType, UnifiedMindtraceODM
from mindtrace.jobs import Job, JobSchema, Orchestrator, RabbitMQClient
from mindtrace.registry import Registry
from mindtrace.registry.backends.minio_registry_backend import MinioRegistryBackend
from mindtrace.registry.core.types import OnConflict
from mindtrace.services import EndpointSpec, Gateway, ServerStatus

# -- ClusterManager endpoint schemas --
_CM_SCHEMAS = {
    "submit_job": TaskSchema(name="submit_job", input_schema=Job, output_schema=cluster_types.JobStatus),
    "register_job_to_endpoint": TaskSchema(
        name="register_job_to_endpoint", input_schema=cluster_types.RegisterJobToEndpointInput
    ),
    "register_job_to_worker": TaskSchema(
        name="register_job_to_worker", input_schema=cluster_types.RegisterJobToWorkerInput
    ),
    "get_job_status": TaskSchema(
        name="get_job_status", input_schema=cluster_types.GetJobStatusInput, output_schema=cluster_types.JobStatus
    ),
    "worker_alert_started_job": TaskSchema(
        name="worker_alert_started_job", input_schema=cluster_types.WorkerAlertStartedJobInput
    ),
    "worker_alert_completed_job": TaskSchema(
        name="worker_alert_completed_job", input_schema=cluster_types.WorkerAlertCompletedJobInput
    ),
    "register_node": TaskSchema(
        name="register_node",
        input_schema=cluster_types.RegisterNodeInput,
        output_schema=cluster_types.RegisterNodeOutput,
    ),
    "register_worker_type": TaskSchema(name="register_worker_type", input_schema=cluster_types.RegisterWorkerTypeInput),
    "launch_worker": TaskSchema(
        name="launch_worker",
        input_schema=cluster_types.ClusterLaunchWorkerInput,
        output_schema=cluster_types.ClusterLaunchWorkerOutput,
    ),
    "launch_worker_status": TaskSchema(
        name="launch_worker_status",
        input_schema=cluster_types.ClusterLaunchWorkerStatusInput,
        output_schema=cluster_types.ClusterLaunchWorkerStatusOutput,
    ),
    "clear_databases": TaskSchema(name="clear_databases"),
    "register_job_schema_to_worker_type": TaskSchema(
        name="register_job_schema_to_worker_type", input_schema=cluster_types.RegisterJobSchemaToWorkerTypeInput
    ),
    "get_worker_status": TaskSchema(
        name="get_worker_status",
        input_schema=cluster_types.GetWorkerStatusInput,
        output_schema=cluster_types.WorkerStatus,
    ),
    "get_worker_status_by_url": TaskSchema(
        name="get_worker_status_by_url",
        input_schema=cluster_types.GetWorkerStatusByUrlInput,
        output_schema=cluster_types.WorkerStatus,
    ),
    "query_worker_status": TaskSchema(
        name="query_worker_status",
        input_schema=cluster_types.QueryWorkerStatusInput,
        output_schema=cluster_types.WorkerStatus,
    ),
    "query_worker_status_by_url": TaskSchema(
        name="query_worker_status_by_url",
        input_schema=cluster_types.QueryWorkerStatusByUrlInput,
        output_schema=cluster_types.WorkerStatus,
    ),
    "clear_job_schema_queue": TaskSchema(
        name="clear_job_schema_queue", input_schema=cluster_types.ClearJobSchemaQueueInput
    ),
    "get_dlq_jobs": TaskSchema(name="get_dlq_jobs", output_schema=cluster_types.GetDLQJobsOutput),
    "requeue_from_dlq": TaskSchema(
        name="requeue_from_dlq", input_schema=cluster_types.RequeueFromDLQInput, output_schema=cluster_types.JobStatus
    ),
    "discard_from_dlq": TaskSchema(name="discard_from_dlq", input_schema=cluster_types.DiscardFromDLQInput),
}


class ClusterManager(Gateway):
    _endpoint_specs = [
        EndpointSpec(path="submit_job", method_name="submit_job", schema=_CM_SCHEMAS["submit_job"]),
        EndpointSpec(
            path="register_job_to_endpoint",
            method_name="register_job_to_endpoint",
            schema=_CM_SCHEMAS["register_job_to_endpoint"],
        ),
        EndpointSpec(
            path="register_job_to_worker",
            method_name="register_job_to_worker",
            schema=_CM_SCHEMAS["register_job_to_worker"],
        ),
        EndpointSpec(path="get_job_status", method_name="get_job_status", schema=_CM_SCHEMAS["get_job_status"]),
        EndpointSpec(
            path="worker_alert_started_job",
            method_name="worker_alert_started_job",
            schema=_CM_SCHEMAS["worker_alert_started_job"],
        ),
        EndpointSpec(
            path="worker_alert_completed_job",
            method_name="worker_alert_completed_job",
            schema=_CM_SCHEMAS["worker_alert_completed_job"],
        ),
        EndpointSpec(path="register_node", method_name="register_node", schema=_CM_SCHEMAS["register_node"]),
        EndpointSpec(
            path="register_worker_type", method_name="register_worker_type", schema=_CM_SCHEMAS["register_worker_type"]
        ),
        EndpointSpec(path="launch_worker", method_name="launch_worker", schema=_CM_SCHEMAS["launch_worker"]),
        EndpointSpec(
            path="launch_worker_status", method_name="launch_worker_status", schema=_CM_SCHEMAS["launch_worker_status"]
        ),
        EndpointSpec(path="clear_databases", method_name="clear_databases", schema=_CM_SCHEMAS["clear_databases"]),
        EndpointSpec(
            path="register_job_schema_to_worker_type",
            method_name="register_job_schema_to_worker_type",
            schema=_CM_SCHEMAS["register_job_schema_to_worker_type"],
        ),
        EndpointSpec(
            path="get_worker_status", method_name="get_worker_status", schema=_CM_SCHEMAS["get_worker_status"]
        ),
        EndpointSpec(
            path="get_worker_status_by_url",
            method_name="get_worker_status_by_url",
            schema=_CM_SCHEMAS["get_worker_status_by_url"],
        ),
        EndpointSpec(
            path="query_worker_status", method_name="query_worker_status", schema=_CM_SCHEMAS["query_worker_status"]
        ),
        EndpointSpec(
            path="query_worker_status_by_url",
            method_name="query_worker_status_by_url",
            schema=_CM_SCHEMAS["query_worker_status_by_url"],
        ),
        EndpointSpec(
            path="clear_job_schema_queue",
            method_name="clear_job_schema_queue",
            schema=_CM_SCHEMAS["clear_job_schema_queue"],
        ),
        EndpointSpec(path="get_dlq_jobs", method_name="get_dlq_jobs", schema=_CM_SCHEMAS["get_dlq_jobs"]),
        EndpointSpec(path="requeue_from_dlq", method_name="requeue_from_dlq", schema=_CM_SCHEMAS["requeue_from_dlq"]),
        EndpointSpec(path="discard_from_dlq", method_name="discard_from_dlq", schema=_CM_SCHEMAS["discard_from_dlq"]),
    ]

    def __init__(self, minio_endpoint=None, **kwargs):
        """
        Args:
            minio_endpoint: str | None: the location of the minio server to use for the registry.
                If None, use MINDTRACE_CLUSTER.MINIO_HOST and MINDTRACE_CLUSTER.MINIO_PORT
        """
        super().__init__(**kwargs)
        rabbitmq_password = (
            self.config.get_secret("MINDTRACE_CLUSTER", "RABBITMQ_PASSWORD")
            or self.config["MINDTRACE_CLUSTER"]["RABBITMQ_PASSWORD"]
        )
        self.orchestrator = Orchestrator(
            backend=RabbitMQClient(
                host=self.config["MINDTRACE_CLUSTER"]["RABBITMQ_HOST"],
                port=self.config["MINDTRACE_CLUSTER"]["RABBITMQ_PORT"],
                username=self.config["MINDTRACE_CLUSTER"]["RABBITMQ_USERNAME"],
                password=rabbitmq_password,
            )
        )
        self.redis_url = self.config["MINDTRACE_CLUSTER"]["DEFAULT_REDIS_URL"]
        self.job_schema_targeting_database = UnifiedMindtraceODM(
            unified_model_cls=cluster_types.JobSchemaTargeting,
            redis_url=self.redis_url,
            preferred_backend=BackendType.REDIS,
        )
        self.job_schema_targeting_database.initialize_sync()
        self.job_status_database = UnifiedMindtraceODM(
            unified_model_cls=cluster_types.JobStatus, redis_url=self.redis_url, preferred_backend=BackendType.REDIS
        )
        self.job_status_database.initialize_sync()
        self.dlq_database = UnifiedMindtraceODM(
            unified_model_cls=cluster_types.DLQJobStatus,
            redis_url=self.redis_url,
            preferred_backend=BackendType.REDIS,
        )
        self.dlq_database.initialize_sync()
        self.worker_auto_connect_database = UnifiedMindtraceODM(
            unified_model_cls=cluster_types.WorkerAutoConnect,
            redis_url=self.redis_url,
            preferred_backend=BackendType.REDIS,
        )
        self.worker_auto_connect_database.initialize_sync()
        self.worker_status_database = UnifiedMindtraceODM(
            unified_model_cls=cluster_types.WorkerStatus,
            redis_url=self.redis_url,
            preferred_backend=BackendType.REDIS,
        )
        self.worker_status_database.initialize_sync()
        self.worker_registry_uri = self.config["MINDTRACE_CLUSTER"]["MINIO_REGISTRY_URI"]
        # Derive Minio host/port from either explicit endpoint override or cluster config.
        if minio_endpoint is not None:
            parsed_minio = urllib.parse.urlparse(minio_endpoint)
            if parsed_minio.hostname:
                self.worker_registry_host = parsed_minio.hostname
                self.worker_registry_port = parsed_minio.port or 9000
            else:
                # Handle host:port or bare host for backward compatibility
                host, _, port_str = minio_endpoint.partition(":")
                self.worker_registry_host = host or "localhost"
                self.worker_registry_port = int(port_str) if port_str else 9000
        else:
            self.worker_registry_host = self.config["MINDTRACE_CLUSTER"]["MINIO_HOST"]
            self.worker_registry_port = int(self.config["MINDTRACE_CLUSTER"]["MINIO_PORT"])

        self.worker_registry_endpoint = f"{self.worker_registry_host}:{self.worker_registry_port}"
        self.worker_registry_access_key = self.config["MINDTRACE_CLUSTER"]["MINIO_ACCESS_KEY"]
        self.worker_registry_secret_key = self.config.get_secret("MINDTRACE_CLUSTER", "MINIO_SECRET_KEY")
        self.worker_registry_bucket = self.config["MINDTRACE_CLUSTER"]["MINIO_BUCKET"]
        self.nodes = []
        minio_backend = MinioRegistryBackend(
            uri=self.worker_registry_uri,
            endpoint=self.worker_registry_endpoint,
            access_key=self.worker_registry_access_key,
            secret_key=self.worker_registry_secret_key,
            bucket=self.worker_registry_bucket,
            secure=False,
        )
        self.worker_registry = Registry(backend=minio_backend, mutable=True)
        self.worker_registry.register_materializer(
            cluster_types.ProxyWorker, "mindtrace.cluster.StandardWorkerLauncher"
        )

    def register_job_to_endpoint(self, payload: cluster_types.RegisterJobToEndpointInput):
        """
        Register a job schema to an endpoint. Jobs of this type will be routed directly to the endpoint.

        Args:
            payload (RegisterJobToEndpointInput): The payload containing the job type and endpoint.
        """
        for entry in self.job_schema_targeting_database.find(
            self.job_schema_targeting_database.redis_backend.model_cls.schema_name == payload.job_type
        ):
            self.logger.info(
                f"Deleting old job schema targeting for job type {payload.job_type} from endpoint {entry.target_endpoint}"
            )
            self.job_schema_targeting_database.delete(entry.pk)
        self.job_schema_targeting_database.insert(
            cluster_types.JobSchemaTargeting(schema_name=payload.job_type, target_endpoint=payload.endpoint)
        )
        self.logger.info(f"Registered {payload.job_type} to {payload.endpoint}")

    def _submit_job_to_endpoint(self, job: Job, endpoint: str):
        """
        Submit a job to the appropriate endpoint.

        Args:
            job (Job): The job to submit.

        Returns:
            JobOutput: The output of the job.
        """

        job_status = cluster_types.JobStatus(
            job_id=job.id, status=cluster_types.JobStatusEnum.RUNNING, output={}, worker_id=endpoint, job=job
        )
        endpoint_url = f"{self._url}{endpoint}"
        self.job_status_database.insert(job_status)
        self.logger.info(f"Submitted job {job.id} to {endpoint_url}")

        response = requests.post(endpoint_url, json=job.model_dump(), timeout=60)

        if response.status_code != 200:
            raise RuntimeError(f"Gateway proxy request failed: {response.text}")

        # Parse response
        try:
            result = response.json()
        except Exception:
            result = {"status": "completed", "output": {}}

        status_str = result.get("status") or "completed"
        job_status.status = cluster_types.JobStatusEnum(status_str)
        job_status.output = result.get("output") or {}
        self.job_status_database.insert(job_status)
        self.logger.info(f"Completed job {job.id} with status {job_status.status}")
        return job_status

    def submit_job(self, job: Job):
        """
        Submit a job to the cluster. Will route to the appropriate endpoint based on the job type, or to the Orchestrator.

        Args:
            job (Job): The job to submit.

        Returns:
            JobOutput: The output of the job.
        """

        job_schema_targeting_list = self.job_schema_targeting_database.find(
            self.job_schema_targeting_database.redis_backend.model_cls.schema_name == job.schema_name
        )

        job_status_list = self.job_status_database.find(
            self.job_status_database.redis_backend.model_cls.job_id == job.id
        )
        if not job_status_list:
            job_status = cluster_types.JobStatus(
                job_id=job.id, status=cluster_types.JobStatusEnum.QUEUED, output={}, worker_id="", job=job
            )
        else:
            job_status = job_status_list[0]
            job_status.status = cluster_types.JobStatusEnum.QUEUED
            job_status.worker_id = ""

        if not job_schema_targeting_list:
            self.logger.error(f"No job schema targeting found for job type {job.schema_name}")
            job_status.status = cluster_types.JobStatusEnum.ERROR
            job_status.output = {"error": f"No job schema targeting found for job type {job.schema_name}"}
            self.job_status_database.insert(job_status)
            return job_status

        self.job_status_database.insert(job_status)

        job_schema_targeting = job_schema_targeting_list[0]
        if job_schema_targeting.target_endpoint == "@orchestrator":
            self.logger.info(f"Submitting job {job.id} to orchestrator")
            self.orchestrator.publish(job.schema_name, job)
            return job_status
        return self._submit_job_to_endpoint(job, job_schema_targeting.target_endpoint)

    def register_job_to_worker(self, payload: dict):
        """
        Register a job to an (already launched) Worker instance.
        This will connect the worker to the Orchestrator and listen on the appropriate queue for this job type.

        Args:
            job_type (str): The type of job to register.
            worker_url (str): The URL of the worker to register the job to.
        """
        from mindtrace.cluster.core.worker import Worker

        job_type = payload["job_type"]
        worker_url = payload["worker_url"]
        for entry in self.job_schema_targeting_database.find(
            self.job_schema_targeting_database.redis_backend.model_cls.schema_name == job_type
        ):
            self.logger.info(
                f"Deleting old job schema targeting for job type {job_type} from endpoint {entry.target_endpoint}"
            )
            try:
                self.job_schema_targeting_database.delete(entry.pk)
            except Exception as e:
                self.logger.warning(
                    f"Failed to delete job schema targeting for job type {job_type} from endpoint {entry.target_endpoint}: {e}"
                )
        self.job_schema_targeting_database.insert(
            cluster_types.JobSchemaTargeting(schema_name=job_type, target_endpoint="@orchestrator")
        )
        self.orchestrator.register(JobSchema(name=job_type, input_schema=BaseModel))
        worker_cm = Worker.connect(worker_url)

        heartbeat = worker_cm.heartbeat().heartbeat
        if heartbeat.status == ServerStatus.DOWN:
            self.logger.warning(f"Worker {worker_url} is down, not registering to cluster")
            return

        worker_cm.connect_to_cluster(
            backend_args=self.orchestrator.backend.consumer_backend_args,
            queue_name=job_type,
            cluster_url=str(self._url),
        )
        worker_id = str(heartbeat.server_id)
        worker_status_list = self.worker_status_database.find(
            self.worker_status_database.redis_backend.model_cls.worker_id == worker_id
        )
        if not worker_status_list:
            self.worker_status_database.insert(
                cluster_types.WorkerStatus(
                    worker_id=worker_id,
                    worker_type=job_type,
                    worker_url=worker_url,
                    status=cluster_types.WorkerStatusEnum.IDLE,
                    job_id=None,
                    last_heartbeat=datetime.now(),
                )
            )
        self.logger.info(f"Connected {worker_url} to cluster {str(self._url)} listening on queue {job_type}")

    def register_worker_type(self, payload: dict):
        """
        Register a worker type to the cluster. This will allow Workers of this type to be launched on Nodes.
        If the
        Args:
            payload (dict): The payload containing the worker name, worker class, and worker params.
        """
        worker_name = payload["worker_name"]
        worker_class = payload["worker_class"]
        worker_params = payload["worker_params"]
        git_repo_url = payload.get("git_repo_url", None)
        git_branch = payload.get("git_branch", None)
        git_commit = payload.get("git_commit", None)
        git_working_dir = payload.get("git_working_dir", None)
        git_depth = payload.get("git_depth", None)
        job_schema_name = payload["job_type"]
        proxy_worker = cluster_types.ProxyWorker(
            worker_type=worker_class,
            worker_params=worker_params,
            git_repo_url=git_repo_url,
            git_branch=git_branch,
            git_commit=git_commit,
            git_working_dir=git_working_dir,
            git_depth=git_depth,
        )
        self.worker_registry.save(f"worker:{worker_name}", proxy_worker, on_conflict=OnConflict.OVERWRITE)
        if job_schema_name:
            self.register_job_schema_to_worker_type({"job_schema_name": job_schema_name, "worker_type": worker_name})

    def register_job_schema_to_worker_type(self, payload: dict):
        """
        Register a job schema to a worker type. This will allow Jobs of this type to be routed to the worker type.
        """
        if not self.worker_registry.has_object(f"worker:{payload['worker_type']}"):
            self.logger.warning(f"Worker type {payload['worker_type']} not found in registry")
            return

        job_schema_name = payload["job_schema_name"]
        worker_type = payload["worker_type"]

        # Ensure the job type is routed via the orchestrator.
        self.job_schema_targeting_database.insert(
            cluster_types.JobSchemaTargeting(schema_name=job_schema_name, target_endpoint="@orchestrator")
        )
        # Enable auto-connect so that future launches of this worker type are automatically
        # wired up to the appropriate queue.
        self.worker_auto_connect_database.insert(
            cluster_types.WorkerAutoConnect(worker_type=worker_type, schema_name=job_schema_name)
        )
        # Critically, declare the orchestrator queue up-front so that jobs submitted
        # before any worker is launched are durably enqueued and can be consumed once
        # a worker connects.
        self.orchestrator.register(JobSchema(name=job_schema_name, input_schema=BaseModel))
        self.logger.info(f"Registered job schema {job_schema_name} to worker type {worker_type}")

    def get_job_status(self, payload: dict):
        """
        Get the status of a job. Does not query the worker, only the database.

        Args:
            payload (dict): The payload containing the job id.

        Returns:
            JobStatus: The status of the job.
        """
        job_id = payload["job_id"]
        job_status_list = self.job_status_database.find(
            self.job_status_database.redis_backend.model_cls.job_id == job_id
        )
        if not job_status_list:
            raise ValueError(f"Job status not found for job id {job_id}")
        return job_status_list[0]

    def get_worker_status(self, payload: dict):
        """
        Get the status of a worker.
        """
        worker_id = payload["worker_id"]
        worker_status_list = self.worker_status_database.find(
            self.worker_status_database.redis_backend.model_cls.worker_id == worker_id
        )
        if not worker_status_list:
            return cluster_types.WorkerStatus(
                worker_id=worker_id,
                worker_type="",
                worker_url="",
                status=cluster_types.WorkerStatusEnum.NONEXISTENT,
                job_id=None,
                last_heartbeat=None,
            )
        return worker_status_list[0]

    def get_worker_status_by_url(self, payload: dict):
        """
        Get the status of a worker.
        """
        worker_url = payload["worker_url"]
        worker_id = self._url_to_id(worker_url)
        if worker_id is None:
            return cluster_types.WorkerStatus(
                worker_id="",
                worker_type="",
                worker_url=worker_url,
                status=cluster_types.WorkerStatusEnum.NONEXISTENT,
                job_id=None,
                last_heartbeat=None,
            )
        return self.get_worker_status(payload={"worker_id": worker_id})

    def query_worker_status(self, payload: dict):
        """
        Query the status of a worker.
        """
        from mindtrace.cluster.core.worker import Worker

        worker_id = payload["worker_id"]
        worker_status_list = self.worker_status_database.find(
            self.worker_status_database.redis_backend.model_cls.worker_id == worker_id
        )
        if not worker_status_list:
            return cluster_types.WorkerStatus(
                worker_id=worker_id,
                worker_type="",
                worker_url="",
                status=cluster_types.WorkerStatusEnum.NONEXISTENT,
                job_id=None,
                last_heartbeat=None,
            )
        worker_url = worker_status_list[0].worker_url
        try:
            worker_cm = Worker.connect(worker_url)
        except Exception:
            worker_cm = None
        if worker_cm is None or worker_cm.heartbeat().heartbeat.status == ServerStatus.DOWN:
            our_status = update_database(
                self.worker_status_database,
                "worker_id",
                worker_id,
                {
                    "status": cluster_types.WorkerStatusEnum.NONEXISTENT,
                    "job_id": None,
                    "last_heartbeat": datetime.now(),
                },
            )
            return our_status
        worker_status = worker_cm.get_status()
        our_status = update_database(
            self.worker_status_database,
            "worker_id",
            worker_id,
            {"status": worker_status.status, "job_id": worker_status.job_id, "last_heartbeat": datetime.now()},
        )
        return our_status

    def query_worker_status_by_url(self, payload: dict):
        """
        Query the status of a worker.
        """
        worker_url = payload["worker_url"]
        worker_id = self._url_to_id(worker_url)
        if worker_id is None:
            return cluster_types.WorkerStatus(
                worker_id="",
                worker_type="",
                worker_url=worker_url or "",
                status=cluster_types.WorkerStatusEnum.NONEXISTENT,
                job_id=None,
                last_heartbeat=None,
            )
        return self.query_worker_status(payload={"worker_id": worker_id})

    def _url_to_id(self, worker_url: str):
        """
        Convert a worker URL to a worker ID.
        """
        worker_status_list = self.worker_status_database.find(
            self.worker_status_database.redis_backend.model_cls.worker_url == worker_url
        )
        if not worker_status_list:
            return None
        return worker_status_list[0].worker_id

    def worker_alert_started_job(self, payload: dict):
        """
        Alert the cluster manager that a job has started.

        Args:
            payload (dict): The payload containing the job id and the worker id that started the job.
        """
        job_id = payload["job_id"]
        update_database(
            self.job_status_database,
            "job_id",
            job_id,
            {
                "status": cluster_types.JobStatusEnum.RUNNING,
                "worker_id": payload["worker_id"],
                "job.started_at": datetime.now().isoformat(),
            },
        )
        update_database(
            self.worker_status_database,
            "worker_id",
            payload["worker_id"],
            {"status": cluster_types.WorkerStatusEnum.RUNNING, "job_id": job_id, "last_heartbeat": datetime.now()},
        )
        self.logger.info(f"Worker {payload['worker_id']} alerted cluster manager that job {job_id} has started")

    def worker_alert_completed_job(self, payload: dict):
        """
        Alert the cluster manager that a job has completed.

        Args:
            payload (dict): The payload containing the job id and the output of the job.
        """
        job_id = payload["job_id"]
        self.logger.info(f"Worker {payload['worker_id']} alerted cluster manager that job {job_id} has completed")
        status_enum = cluster_types.JobStatusEnum(payload["status"])
        job_status = update_database(
            self.job_status_database,
            "job_id",
            job_id,
            {"status": status_enum, "output": payload["output"], "job.completed_at": datetime.now().isoformat()},
        )
        if job_status.worker_id != payload["worker_id"]:
            self.logger.warning(
                f"Worker {payload['worker_id']} alerted cluster manager that job {job_id} has completed, but the worker id does not match the stored worker id {job_status.worker_id}"
            )
        if (
            job_status.status == cluster_types.JobStatusEnum.ERROR
            or job_status.status == cluster_types.JobStatusEnum.FAILED
        ):
            self.logger.error(
                f"Job {job_id} has failed, adding to DLQ. Schema: {job_status.job.schema_name}, worker id: {payload['worker_id']}, output: {payload['output']}"
            )
            self.dlq_database.insert(
                cluster_types.DLQJobStatus(
                    job_id=job_id,
                    output=job_status.output,
                    job=job_status.job,
                )
            )

        update_database(
            self.worker_status_database,
            "worker_id",
            payload["worker_id"],
            {"status": cluster_types.WorkerStatusEnum.IDLE, "job_id": None, "last_heartbeat": datetime.now()},
        )

    def requeue_from_dlq(self, payload: dict):
        """
        Requeue a job from the DLQ.
        """
        job_id = payload["job_id"]
        job_status_list = self.dlq_database.find(self.dlq_database.redis_backend.model_cls.job_id == job_id)
        if not job_status_list or len(job_status_list) != 1:
            raise ValueError(f"Job not found in DLQ for job id {job_id}")
        job_status = job_status_list[0]
        self.dlq_database.delete(job_status.pk)
        job = job_status.job
        job.started_at = None
        job.completed_at = None
        job.error = None
        job_status_requeued = self.submit_job(job)
        self.logger.info(f"Requeued job {job_id} from DLQ")
        return job_status_requeued

    def discard_from_dlq(self, payload: dict):
        """
        Discard a job from the DLQ.
        """
        job_id = payload["job_id"]
        job_status_list = self.dlq_database.find(self.dlq_database.redis_backend.model_cls.job_id == job_id)
        if not job_status_list or len(job_status_list) != 1:
            raise ValueError(f"Job not found in DLQ for job id {job_id}")
        job_status = job_status_list[0]
        self.dlq_database.delete(job_status.pk)
        self.logger.info(f"Discarded job {job_id} from DLQ")

    def get_dlq_jobs(self):
        """
        Get all jobs in the DLQ.
        """
        return {"jobs": self.dlq_database.all()}

    def register_node(self, payload: dict):
        """
        Register a node to the cluster. This returns the Minio parameters for the node to be used in the Worker registry.

        Args:
            node_id (str): The id of the node.
        """
        self.nodes.append(payload["node_url"])
        return {
            "endpoint": self.worker_registry_endpoint,
            "access_key": self.worker_registry_access_key,
            "secret_key": self.worker_registry_secret_key,
            "bucket": self.worker_registry_bucket,
            "minio_port": self.worker_registry_port,
            "rabbitmq_host": self.config["MINDTRACE_CLUSTER"]["RABBITMQ_HOST"],
            "rabbitmq_port": self.config["MINDTRACE_CLUSTER"]["RABBITMQ_PORT"],
            "rabbitmq_username": self.config["MINDTRACE_CLUSTER"]["RABBITMQ_USERNAME"],
            "rabbitmq_password": self.config.get_secret("MINDTRACE_CLUSTER", "RABBITMQ_PASSWORD"),
        }

    def launch_worker(self, payload: dict):
        """
        Launch a worker on a node asynchronously. If the worker type is registered to a job schema,
        the worker will be automatically connected to the job schema once it is ready.

        Args:
            payload (dict): The payload containing the node URL, worker type, worker URL, and (optional) worker name.
        """
        from mindtrace.cluster.core.node import Node

        node_url = payload["node_url"]
        worker_type = payload["worker_type"]
        worker_url = payload["worker_url"]
        worker_name = payload["worker_name"]
        node_cm = Node.connect(node_url)
        # If this worker type has an auto-connect entry, pass the job type down to the node
        auto_connect_list = self.worker_auto_connect_database.find(
            self.worker_auto_connect_database.redis_backend.model_cls.worker_type == worker_type
        )
        auto_connect_job_type = auto_connect_list[0].schema_name if auto_connect_list else None

        output = node_cm.launch_worker(
            worker_type=worker_type,
            worker_url=worker_url,
            worker_name=worker_name,
            auto_connect_job_type=auto_connect_job_type,
        )
        return {
            "launch_id": output.launch_id,
        }

    def launch_worker_status(self, payload: dict):
        """
        Proxy launch status queries to the appropriate node.
        """
        from mindtrace.cluster.core.node import Node

        node_url = payload["node_url"]
        launch_id = payload["launch_id"]
        node_cm = Node.connect(node_url)
        return node_cm.launch_worker_status(launch_id=launch_id)

    def clear_databases(self):
        """
        Clear all databases.
        """
        for db in [
            self.job_schema_targeting_database,
            self.job_status_database,
            self.dlq_database,
            self.worker_auto_connect_database,
            self.worker_status_database,
        ]:
            for entry in db.all():
                db.delete(entry.pk)
        self.logger.info("Cleared all cluster manager databases")

    def clear_job_schema_queue(self, payload: dict):
        """
        Clear the queue related to a job schema.
        Args:
            job_schema_name: str: the name of the job schema
        """
        queue_name = payload["job_schema_name"]
        self.orchestrator.clean_queue(queue_name)

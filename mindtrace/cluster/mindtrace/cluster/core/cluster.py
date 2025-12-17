import json
import threading
import urllib.parse
import uuid
from abc import abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from fastapi import HTTPException
from pydantic import BaseModel

from mindtrace.cluster.core import types as cluster_types
from mindtrace.cluster.workers.environments.git_env import GitEnvironment
from mindtrace.core import TaskSchema, Timeout, get_class, ifnone
from mindtrace.database import BackendType, UnifiedMindtraceODM
from mindtrace.jobs import Consumer, Job, JobSchema, Orchestrator, RabbitMQClient
from mindtrace.registry import Archiver, Registry
from mindtrace.registry.backends.minio_registry_backend import MinioRegistryBackend
from mindtrace.services import ConnectionManager, Gateway, ServerStatus, Service


def update_database(database: UnifiedMindtraceODM, sort_key: str, find_key: str, update_dict: dict):
    entries = database.find(getattr(database.redis_backend.model_cls, sort_key) == find_key)
    if len(entries) != 1:
        raise ValueError(f"Expected 1 entry for {sort_key} == {find_key}, got {len(entries)}")
    entry = entries[0]
    for key, value in update_dict.items():
        setattr(entry, key, value)
    database.insert(entry)
    return entry


class ClusterManager(Gateway):
    def __init__(self, minio_endpoint=None, **kwargs):
        """
        Args:
            minio_endpoint: str | None: the location of the minio server to use for the registry. If None, use MINDTRACE_CLUSTER_MINIO_ENDPOINT
        """
        super().__init__(**kwargs)
        if kwargs.get("live_service", True):
            self.orchestrator = Orchestrator(
                backend=RabbitMQClient(
                    host=self.config["MINDTRACE_CLUSTER"]["RABBITMQ_HOST"],
                    port=self.config["MINDTRACE_CLUSTER"]["RABBITMQ_PORT"],
                    username=self.config["MINDTRACE_CLUSTER"]["RABBITMQ_USERNAME"],
                    password=self.config["MINDTRACE_CLUSTER"]["RABBITMQ_PASSWORD"],
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
            self.worker_registry_endpoint = ifnone(minio_endpoint, self.config["MINDTRACE_CLUSTER"]["MINIO_ENDPOINT"])
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
            self.worker_registry = Registry(backend=minio_backend)
            self.worker_registry.register_materializer(
                cluster_types.ProxyWorker, "mindtrace.cluster.StandardWorkerLauncher"
            )
        self.add_endpoint(
            "/submit_job",
            func=self.submit_job,
            schema=TaskSchema(name="submit_job", input_schema=Job, output_schema=cluster_types.JobStatus),
            methods=["POST"],
        )
        self.add_endpoint(
            "/register_job_to_endpoint",
            func=self.register_job_to_endpoint,
            schema=TaskSchema(name="register_job_to_endpoint", input_schema=cluster_types.RegisterJobToEndpointInput),
            methods=["POST"],
        )
        self.add_endpoint(
            "/register_job_to_worker",
            func=self.register_job_to_worker,
            schema=TaskSchema(name="register_job_to_worker", input_schema=cluster_types.RegisterJobToWorkerInput),
            methods=["POST"],
        )
        self.add_endpoint(
            "/get_job_status",
            func=self.get_job_status,
            schema=TaskSchema(
                name="get_job_status",
                input_schema=cluster_types.GetJobStatusInput,
                output_schema=cluster_types.JobStatus,
            ),
            methods=["POST"],
        )
        self.add_endpoint(
            "/worker_alert_started_job",
            func=self.worker_alert_started_job,
            schema=TaskSchema(name="worker_alert_started_job", input_schema=cluster_types.WorkerAlertStartedJobInput),
            methods=["POST"],
        )
        self.add_endpoint(
            "/worker_alert_completed_job",
            func=self.worker_alert_completed_job,
            schema=TaskSchema(
                name="worker_alert_completed_job", input_schema=cluster_types.WorkerAlertCompletedJobInput
            ),
            methods=["POST"],
        )
        self.add_endpoint(
            "/register_node",
            func=self.register_node,
            schema=TaskSchema(
                name="register_node",
                input_schema=cluster_types.RegisterNodeInput,
                output_schema=cluster_types.RegisterNodeOutput,
            ),
            methods=["POST"],
        )
        self.add_endpoint(
            "/register_worker_type",
            func=self.register_worker_type,
            schema=TaskSchema(name="register_worker_type", input_schema=cluster_types.RegisterWorkerTypeInput),
            methods=["POST"],
        )
        self.add_endpoint(
            "/launch_worker",
            func=self.launch_worker,
            schema=TaskSchema(
                name="launch_worker",
                input_schema=cluster_types.ClusterLaunchWorkerInput,
                output_schema=cluster_types.ClusterLaunchWorkerOutput,
            ),
            methods=["POST"],
        )
        self.add_endpoint(
            "/clear_databases",
            func=self.clear_databases,
            schema=TaskSchema(name="clear_databases"),
            methods=["POST"],
        )
        self.add_endpoint(
            "/register_job_schema_to_worker_type",
            func=self.register_job_schema_to_worker_type,
            schema=TaskSchema(
                name="register_job_schema_to_worker_type", input_schema=cluster_types.RegisterJobSchemaToWorkerTypeInput
            ),
            methods=["POST"],
        )
        self.add_endpoint(
            "/get_worker_status",
            func=self.get_worker_status,
            schema=TaskSchema(
                name="get_worker_status",
                input_schema=cluster_types.GetWorkerStatusInput,
                output_schema=cluster_types.WorkerStatus,
            ),
            methods=["POST"],
        )
        self.add_endpoint(
            "/get_worker_status_by_url",
            func=self.get_worker_status_by_url,
            schema=TaskSchema(
                name="get_worker_status_by_url",
                input_schema=cluster_types.GetWorkerStatusByUrlInput,
                output_schema=cluster_types.WorkerStatus,
            ),
            methods=["POST"],
        )
        self.add_endpoint(
            "/query_worker_status",
            func=self.query_worker_status,
            schema=TaskSchema(
                name="query_worker_status",
                input_schema=cluster_types.QueryWorkerStatusInput,
                output_schema=cluster_types.WorkerStatus,
            ),
            methods=["POST"],
        )
        self.add_endpoint(
            "/query_worker_status_by_url",
            func=self.query_worker_status_by_url,
            schema=TaskSchema(
                name="query_worker_status_by_url",
                input_schema=cluster_types.QueryWorkerStatusByUrlInput,
                output_schema=cluster_types.WorkerStatus,
            ),
            methods=["POST"],
        )
        self.add_endpoint(
            "/clear_job_schema_queue",
            func=self.clear_job_schema_queue,
            schema=TaskSchema(
                name="clear_job_schema_queue",
                input_schema=cluster_types.ClearJobSchemaQueueInput,
            ),
            methods=["POST"],
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

        job_status = cluster_types.JobStatus(job_id=job.id, status="running", output={}, worker_id=endpoint)
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

        job_status.status = result.get("status") or "completed"
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
        job_status = cluster_types.JobStatus(job_id=job.id, status="queued", output={}, worker_id="")
        self.job_status_database.insert(job_status)

        job_schema_targeting_list = self.job_schema_targeting_database.find(
            self.job_schema_targeting_database.redis_backend.model_cls.schema_name == job.schema_name
        )
        if not job_schema_targeting_list:
            self.logger.error(f"No job schema targeting found for job type {job.schema_name}")
            return cluster_types.JobStatus(
                job_id=job.id,
                status="error",
                output={"error": f"No job schema targeting found for job type {job.schema_name}"},
                worker_id="",
            )
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
        job_type = payload["job_type"]
        worker_url = payload["worker_url"]
        for entry in self.job_schema_targeting_database.find(
            self.job_schema_targeting_database.redis_backend.model_cls.schema_name == job_type
        ):
            self.logger.info(
                f"Deleting old job schema targeting for job type {job_type} from endpoint {entry.target_endpoint}"
            )
            self.job_schema_targeting_database.delete(entry.pk)
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
        job_schema_name = payload["job_type"]
        proxy_worker = cluster_types.ProxyWorker(
            worker_type=worker_class,
            worker_params=worker_params,
            git_repo_url=git_repo_url,
            git_branch=git_branch,
            git_commit=git_commit,
            git_working_dir=git_working_dir,
        )
        self.worker_registry.save(f"worker:{worker_name}", proxy_worker)
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
        self.job_schema_targeting_database.insert(
            cluster_types.JobSchemaTargeting(schema_name=job_schema_name, target_endpoint="@orchestrator")
        )
        self.worker_auto_connect_database.insert(
            cluster_types.WorkerAutoConnect(worker_type=worker_type, schema_name=job_schema_name)
        )
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
            self.job_status_database, "job_id", job_id, {"status": "running", "worker_id": payload["worker_id"]}
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
        job_status = update_database(
            self.job_status_database, "job_id", job_id, {"status": payload["status"], "output": payload["output"]}
        )
        if job_status.worker_id != payload["worker_id"]:
            self.logger.warning(
                f"Worker {payload['worker_id']} alerted cluster manager that job {job_id} has completed, but the worker id does not match the stored worker id {job_status.worker_id}"
            )
        update_database(
            self.worker_status_database,
            "worker_id",
            payload["worker_id"],
            {"status": cluster_types.WorkerStatusEnum.IDLE, "job_id": None, "last_heartbeat": datetime.now()},
        )

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
        }

    def launch_worker(self, payload: dict):
        """
        Launch a worker on a node. If the worker type is registered to a job schema, the worker will be automatically connected to the job schema.

        Args:
            payload (dict): The payload containing the node URL, worker type, worker URL, and (optional) worker name.
        """
        node_url = payload["node_url"]
        worker_type = payload["worker_type"]
        worker_url = payload["worker_url"]
        worker_name = payload["worker_name"]
        node_cm = Node.connect(node_url)
        output = node_cm.launch_worker(worker_type=worker_type, worker_url=worker_url, worker_name=worker_name)
        worker_auto_connect_list = self.worker_auto_connect_database.find(
            self.worker_auto_connect_database.redis_backend.model_cls.worker_type == worker_type
        )
        if worker_auto_connect_list:
            worker_auto_connect = worker_auto_connect_list[0]
            self.register_job_to_worker(
                payload={"job_type": worker_auto_connect.schema_name, "worker_url": output.worker_url}
            )
        return {
            "worker_id": output.worker_id,
            "worker_name": output.worker_name,
            "worker_url": output.worker_url,
        }

    def clear_databases(self):
        """
        Clear all databases.
        """
        for db in [
            self.job_schema_targeting_database,
            self.job_status_database,
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


class Node(Service):
    def __init__(self, cluster_url: str | None = None, worker_ports: list[int] | None = None, **kwargs):
        super().__init__(**kwargs)
        self.worker_registry: Registry = None  # type: ignore
        self.cluster_url = cluster_url
        if cluster_url is not None:
            self.cluster_cm = ClusterManager.connect(cluster_url)
            minio_params = self.cluster_cm.register_node(node_url=str(self._url))
            minio_backend = MinioRegistryBackend(
                uri=f"~/.cache/mindtrace/minio_registry_node_{self.id}", **minio_params.model_dump(), secure=False
            )
            self.worker_registry = Registry(backend=minio_backend)
            self.node_worker_database: UnifiedMindtraceODM = UnifiedMindtraceODM(
                unified_model_cls=cluster_types.NodeWorker,
                redis_url=self.config["MINDTRACE_CLUSTER"]["DEFAULT_REDIS_URL"],
                preferred_backend=BackendType.REDIS,
            )
            self.node_worker_database.initialize_sync()
        else:
            self.cluster_cm = None  # type: ignore
            self.worker_registry = None  # type: ignore
            self.node_worker_database = None  # type: ignore

        if worker_ports is not None:
            self.worker_ports = worker_ports
        else:
            config_range = self.config["MINDTRACE_CLUSTER"]["WORKER_PORTS_RANGE"]
            self.worker_ports = self._parse_port_range(config_range)
            self.logger.debug(f"Using worker ports range {config_range} for node {self.id}")

        self.add_endpoint(
            "/launch_worker",
            func=self.launch_worker,
            schema=TaskSchema(
                name="launch_worker",
                input_schema=cluster_types.LaunchWorkerInput,
                output_schema=cluster_types.LaunchWorkerOutput,
            ),
            methods=["POST"],
        )
        self.add_endpoint(
            "/shutdown_worker",
            func=self.shutdown_worker,
            schema=TaskSchema(
                name="shutdown_worker",
                input_schema=cluster_types.ShutdownWorkerInput,
            ),
            methods=["POST"],
        )
        self.add_endpoint(
            "/shutdown_worker_by_id",
            func=self.shutdown_worker_by_id,
            schema=TaskSchema(
                name="shutdown_worker_by_id",
                input_schema=cluster_types.ShutdownWorkerByIdInput,
            ),
            methods=["POST"],
        )
        self.add_endpoint(
            "/shutdown_worker_by_port",
            func=self.shutdown_worker_by_port,
            schema=TaskSchema(
                name="shutdown_worker_by_port",
                input_schema=cluster_types.ShutdownWorkerByPortInput,
            ),
            methods=["POST"],
        )
        self.add_endpoint(
            "/shutdown_all_workers",
            func=self.shutdown_all_workers,
            schema=TaskSchema(
                name="shutdown_all_workers",
            ),
            methods=["POST"],
        )

    def _parse_port_range(self, port_range: str) -> list[int]:
        """
        Parse a port range string into a list of ports.
        Args:
            port_range (str): The port range string, e.g. "8080-8090" or "8080,8090".
        Returns:
            list[int]: The list of ports.
        Raises:
            ValueError: If the port range is invalid.
        """
        if "-" in port_range:
            parts = port_range.split("-")
        elif "," in port_range:
            parts = port_range.split(",")
        else:
            raise ValueError(f"Invalid port range: {port_range}: expected separator '-' or ','")
        if len(parts) != 2:
            raise ValueError(f"Invalid port range: {port_range}: expected 'start-end' or 'start,end'")
        start = int(parts[0])
        end = int(parts[1])
        if start > end:
            raise ValueError(f"Invalid port range: {start} > {end}")
        ports = list[int](range(start, end + 1))
        return ports

    def _get_worker_port(self):
        """
        Get a worker port from the list of worker ports.
        """
        for port in self.worker_ports:
            matches = self.node_worker_database.find(
                self.node_worker_database.redis_backend.model_cls.worker_port == port
            )
            if not matches:
                return port
        # see if any worker has crashed so the port is available
        for port in self.worker_ports:
            matches = self.node_worker_database.find(
                self.node_worker_database.redis_backend.model_cls.worker_port == port
            )
            for match in matches:
                try:
                    worker_cm = Worker.connect(match.worker_url)
                    worker_cm.heartbeat()
                except Exception:
                    self.node_worker_database.delete(match.pk)
            matches = self.node_worker_database.find(
                self.node_worker_database.redis_backend.model_cls.worker_port == port
            )
            if not matches:
                return port
        raise ValueError(f"No worker ports available in range {self.worker_ports}")

    def launch_worker(self, payload: dict):
        """
        Launch a worker from the Worker registry.

        Args:
            payload (dict): The payload containing the worker type and worker URL.
                worker_name (optional): str: The name of the worker. If not provided, the worker id will be used.
        Returns:
            LaunchWorkerOutput:
                worker_id: str: The id of the worker.
                worker_name: str: The name of the worker.
                worker_url: str: The URL of the worker.
        Raises:
            ValueError: If no worker ports are available in range.
        """
        worker_type = payload["worker_type"]
        if payload["worker_url"] is None:
            port = self._get_worker_port()
            worker_url = f"http://{self._url.hostname}:{port}"
        else:
            worker_url = payload["worker_url"]
            port = urllib.parse.urlparse(worker_url).port
            if port is None:
                raise ValueError(f"Worker URL {worker_url} does not have a port")
        worker_cm = self.worker_registry.load(f"worker:{worker_type}", url=worker_url)
        worker_id = str(worker_cm.heartbeat().heartbeat.server_id)
        worker_name = payload.get("worker_name")
        if worker_name is None:
            worker_name = worker_id
        self.node_worker_database.insert(
            cluster_types.NodeWorker(
                worker_type=worker_type,
                worker_port=port,
                worker_id=worker_id,
                worker_name=worker_name,
                worker_url=worker_url,
            )
        )
        return {
            "worker_id": worker_id,
            "worker_name": worker_name,
            "worker_url": worker_url,
        }

    def _shutdown_workers(self, entries: list[cluster_types.NodeWorker]):
        """
        Shutdown workers.

        Args:
            entries (list[cluster_types.NodeWorker]): The list of workers to shutdown.
        """
        for entry in entries:
            try:
                worker_cm = Worker.connect(entry.worker_url)
                worker_cm.shutdown()
            except Exception as e:
                self.logger.error(f"Failed to shutdown worker {entry.worker_name}: {e}")
            self.node_worker_database.delete(entry.pk)

    def shutdown_worker(self, payload: dict):
        """
        Shutdown a worker by name.

        Args:
            payload (dict): The payload containing the worker name.
                worker_name (str): The name of the worker to shutdown.
        """
        worker_name = payload["worker_name"]
        entries = self.node_worker_database.find(
            self.node_worker_database.redis_backend.model_cls.worker_name == worker_name
        )
        self._shutdown_workers(entries)

    def shutdown_worker_by_id(self, payload: dict):
        """
        Shutdown a worker by id.

        Args:
            payload (dict): The payload containing the worker id.
                worker_id (str): The id of the worker to shutdown.
        """
        worker_id = payload["worker_id"]
        entries = self.node_worker_database.find(
            self.node_worker_database.redis_backend.model_cls.worker_id == worker_id
        )
        self._shutdown_workers(entries)

    def shutdown_worker_by_port(self, payload: dict):
        """
        Shutdown a worker by port.

        Args:
            payload (dict): The payload containing the worker port.
                worker_port (int): The port of the worker to shutdown.
        """
        worker_port = payload["worker_port"]
        entries = self.node_worker_database.find(
            self.node_worker_database.redis_backend.model_cls.worker_port == worker_port
        )
        self._shutdown_workers(entries)

    def shutdown_all_workers(self):
        """
        Shutdown all workers.
        """
        for entry in self.node_worker_database.all():
            self._shutdown_workers([entry])

    def shutdown(self):
        """
        Shutdown the node and all workers connected to it.
        """
        self.shutdown_all_workers()
        return super().shutdown()


class Worker(Service, Consumer):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if kwargs.get("live_service", True):
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
        self.add_endpoint("/start", self.start, schema=TaskSchema(name="start_worker"))
        self.add_endpoint(
            "/run",
            self.run,
            schema=TaskSchema(
                name="run_worker", input_schema=cluster_types.WorkerRunInput, output_schema=cluster_types.JobStatus
            ),
        )
        self.add_endpoint(
            "/connect_to_cluster",
            self.connect_to_cluster,
            schema=TaskSchema(name="connect_to_cluster", input_schema=cluster_types.ConnectToBackendInput),
        )
        self.add_endpoint(
            "/get_status",
            self.get_status,
            schema=TaskSchema(name="get_status", output_schema=cluster_types.WorkerStatusLocal),
        )
        self.consume_thread = None
        self._cluster_connection_manager = None  # type: ignore
        self._cluster_url = None

    @property
    def cluster_connection_manager(self):
        if self._cluster_connection_manager is None and self._cluster_url is not None:
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
            output = {"status": "failed", "output": {}}
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


class StandardWorkerLauncher(Archiver):
    """This class saves a ProxyWorker to a file, which contains the class name and parameters of the worker.
    When loaded, it will launch the worker and return a ConnectionManager object.
    """

    def __init__(self, uri: str, *args, **kwargs):
        super().__init__(uri=uri, *args, **kwargs)

    def save(self, data: cluster_types.ProxyWorker):
        with open(Path(self.uri) / "worker.json", "w") as f:
            json.dump(data.model_dump(), f)

    def load(self, data_type: Any, url: str) -> ConnectionManager:
        with open(Path(self.uri) / "worker.json", "r") as f:
            worker_dict = json.load(f)
        if worker_dict["git_repo_url"]:
            environment = GitEnvironment(
                repo_url=worker_dict["git_repo_url"],
                branch=worker_dict["git_branch"],
                commit=worker_dict["git_commit"],
                working_dir=worker_dict["git_working_dir"],
            )
            _ = environment.setup()

            # All kwargs (including URL params) go directly to init_params
            init_params = {"url": str(url), **worker_dict["worker_params"]}

            # Strip the URL of the http:// or https:// prefix
            if url.startswith("http://"):
                url_stripped = url[len("http://") :]
            elif url.startswith("https://"):
                url_stripped = url[len("https://") :]
            else:
                url_stripped = url

            # Create launch command
            server_id = uuid.uuid1()
            launch_command = [
                "python",
                "-m",
                "mindtrace.services.core.launcher",
                "-s",
                worker_dict["worker_type"],
                "-w",
                "1",
                "-b",
                url_stripped,
                "-p",
                str(server_id),
                "-k",
                "uvicorn.workers.UvicornWorker",
                "--init-params",
                json.dumps(init_params),
            ]
            pid = environment.execute(launch_command, detach=True)
            self.logger.info(f"Worker {worker_dict['worker_type']} launched on url {url} with pid {pid}")
            timeout_handler = Timeout(
                timeout=60,
                exceptions=(ConnectionRefusedError, requests.exceptions.ConnectionError, HTTPException),
                desc=f"Launching {worker_dict['worker_type']} at {url}",
            )
            try:
                connection_manager = timeout_handler.run(Worker.connect, url=url)
            except Exception as e:
                self.logger.error(f"Failed to connect to worker {worker_dict['worker_type']} at {url}: {e}")
                raise e
            return connection_manager
        else:
            worker_class = get_class(worker_dict["worker_type"])
            return worker_class.launch(url=url, **worker_dict["worker_params"], wait_for_launch=True, timeout=60)

import threading
import urllib.parse
import uuid

from mindtrace.cluster.core import types as cluster_types
from mindtrace.core import TaskSchema
from mindtrace.database import BackendType, UnifiedMindtraceODM
from mindtrace.registry import Registry
from mindtrace.registry.backends.minio_registry_backend import MinioRegistryBackend
from mindtrace.services import Service, endpoint

# -- Node endpoint schemas --
_NODE_SCHEMAS = {
    "launch_worker": TaskSchema(
        name="launch_worker",
        input_schema=cluster_types.LaunchWorkerInput,
        output_schema=cluster_types.LaunchWorkerOutput,
    ),
    "launch_worker_status": TaskSchema(
        name="launch_worker_status",
        input_schema=cluster_types.LaunchWorkerStatusInput,
        output_schema=cluster_types.LaunchWorkerStatusOutput,
    ),
    "shutdown_worker": TaskSchema(name="shutdown_worker", input_schema=cluster_types.ShutdownWorkerInput),
    "shutdown_worker_by_id": TaskSchema(
        name="shutdown_worker_by_id", input_schema=cluster_types.ShutdownWorkerByIdInput
    ),
    "shutdown_worker_by_port": TaskSchema(
        name="shutdown_worker_by_port", input_schema=cluster_types.ShutdownWorkerByPortInput
    ),
    "shutdown_all_workers": TaskSchema(name="shutdown_all_workers"),
}


class Node(Service):
    def __init__(self, cluster_url: str | None = None, worker_ports: list[int] | None = None, **kwargs):
        super().__init__(**kwargs)
        self.worker_registry: Registry = None  # type: ignore
        self.cluster_url = cluster_url
        if cluster_url is not None:
            from mindtrace.cluster.core.cluster_manager import ClusterManager

            # Connect to the cluster and register this node. The response contains
            # Minio and RabbitMQ configuration details (keys, ports, etc.). The
            # externally reachable host is inferred from the cluster_url rather than
            # trusting the cluster manager to know its own hostname.
            self.cluster_cm = ClusterManager.connect(cluster_url)
            register_output = self.cluster_cm.register_node(node_url=str(self._url))
            parsed_cluster_url = urllib.parse.urlparse(cluster_url)
            cluster_host = parsed_cluster_url.hostname or "localhost"

            # Use the Minio port provided by the cluster, but always pair it with the
            # host derived from cluster_url so that nodes work correctly in dockerised
            # environments where the cluster's own hostname may not be externally
            # reachable.
            minio_port = register_output.minio_port
            node_minio_endpoint = f"{cluster_host}:{minio_port}"

            minio_backend = MinioRegistryBackend(
                uri=f"~/.cache/mindtrace/minio_registry_node_{self.id}",
                endpoint=node_minio_endpoint,
                access_key=register_output.access_key,
                secret_key=register_output.secret_key,
                bucket=register_output.bucket,
                secure=False,
            )
            self.worker_registry = Registry(backend=minio_backend)

            # Derive RabbitMQ host from the cluster URL and take the remaining
            # connection details from the cluster response.
            self.rabbitmq_config = {
                "host": cluster_host,
                "port": register_output.rabbitmq_port,
                "username": register_output.rabbitmq_username,
                "password": register_output.rabbitmq_password,
            }
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

        # Track asynchronous worker launches by launch_id and port
        self._launch_status_lock = threading.Lock()
        self._launch_status: dict[str, cluster_types.LaunchWorkerStatusOutput] = {}
        self._launching_ports: set[int] = set()

        if worker_ports is not None:
            self.worker_ports = worker_ports
        else:
            config_range = self.config["MINDTRACE_CLUSTER"]["WORKER_PORTS_RANGE"]
            self.worker_ports = self._parse_port_range(config_range)
            self.logger.debug(f"Using worker ports range {config_range} for node {self.id}")

    @endpoint("launch_worker_status", schema=_NODE_SCHEMAS["launch_worker_status"])
    def launch_worker_status(self, payload: dict):
        """
        Return the status of a previously requested worker launch.
        """
        launch_id = payload["launch_id"]
        with self._launch_status_lock:
            status = self._launch_status.get(launch_id)
        if status is None:
            raise ValueError(f"Unknown launch_id: {launch_id}")
        return status.model_dump()

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
        from mindtrace.cluster.core.worker import Worker

        for port in self.worker_ports:
            if port in self._launching_ports:
                continue
            matches = self.node_worker_database.find(
                self.node_worker_database.redis_backend.model_cls.worker_port == port
            )
            if not matches:
                return port
        # see if any worker has crashed so the port is available
        for port in self.worker_ports:
            if port in self._launching_ports:
                continue
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

    @endpoint("launch_worker", schema=_NODE_SCHEMAS["launch_worker"])
    def launch_worker(self, payload: dict):
        """
        Asynchronously launch a worker from the Worker registry and return a launch_id.

        Args:
            payload (dict): The payload containing the worker type and worker URL.
                worker_name (optional): str: The name of the worker. If not provided, the worker id will be used.

        Returns:
            LaunchWorkerOutput:
                launch_id: str: Identifier that can be used to query launch status.
        """
        worker_type = payload["worker_type"]
        worker_url = payload["worker_url"]
        worker_name = payload.get("worker_name")
        auto_connect_job_type = payload.get("auto_connect_job_type")

        launch_id = str(uuid.uuid4())
        with self._launch_status_lock:
            self._launch_status[launch_id] = cluster_types.LaunchWorkerStatusOutput(
                launch_id=launch_id,
                status=cluster_types.LaunchStatusEnum.PENDING,
            )

        thread = threading.Thread(
            target=self._launch_worker_background,
            args=(launch_id, worker_type, worker_url, worker_name, auto_connect_job_type),
            daemon=True,
        )
        thread.start()

        return {"launch_id": launch_id}

    def _launch_worker_background(
        self,
        launch_id: str,
        worker_type: str,
        worker_url: str | None,
        worker_name: str | None,
        auto_connect_job_type: str | None,
    ) -> None:
        with self._launch_status_lock:
            self._launch_status[launch_id].status = cluster_types.LaunchStatusEnum.RUNNING

        try:
            if worker_url is None:
                port = self._get_worker_port()
                worker_url = f"http://{self._url.hostname}:{port}"
            else:
                port = urllib.parse.urlparse(worker_url).port
                if port is None:
                    raise ValueError(f"Worker URL {worker_url} does not have a port")

            # Mark this port as in the process of launching to avoid reusing it
            # for another auto-selected worker until launch completes.
            self._launching_ports.add(port)

            worker_cm = self.worker_registry.load(f"worker:{worker_type}", url=worker_url)
            worker_id = str(worker_cm.heartbeat().heartbeat.server_id)
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

            # If an auto-connect job type was provided and this node is attached to a cluster,
            # automatically register the worker to the appropriate job schema once it is ready.
            if auto_connect_job_type and self.cluster_cm is not None:
                try:
                    self.cluster_cm.register_job_to_worker(
                        job_type=auto_connect_job_type,
                        worker_url=worker_url,
                    )
                except Exception as auto_connect_error:
                    self.logger.error(
                        f"Auto-connect registration failed for worker {worker_name} at {worker_url}: {auto_connect_error}"
                    )
                    raise auto_connect_error

            status = cluster_types.LaunchWorkerStatusOutput(
                launch_id=launch_id,
                status=cluster_types.LaunchStatusEnum.READY,
                worker_id=worker_id,
                worker_name=worker_name,
                worker_url=worker_url,
            )
        except Exception as e:
            self.logger.error(f"Failed to launch worker {worker_type}: {e}")
            status = cluster_types.LaunchWorkerStatusOutput(
                launch_id=launch_id,
                status=cluster_types.LaunchStatusEnum.FAILED,
                error=str(e),
            )

        with self._launch_status_lock:
            self._launch_status[launch_id] = status
        # Always clear the launching port marker once the launch attempt is finished.
        if "port" in locals():
            self._launching_ports.discard(port)

    def _shutdown_workers(self, entries: list[cluster_types.NodeWorker]):
        """
        Shutdown workers.

        Args:
            entries (list[cluster_types.NodeWorker]): The list of workers to shutdown.
        """
        from mindtrace.cluster.core.worker import Worker

        for entry in entries:
            try:
                worker_cm = Worker.connect(entry.worker_url)
                worker_cm.shutdown()
            except Exception as e:
                self.logger.error(f"Failed to shutdown worker {entry.worker_name}: {e}")
            self.node_worker_database.delete(entry.pk)

    @endpoint("shutdown_worker", schema=_NODE_SCHEMAS["shutdown_worker"])
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

    @endpoint("shutdown_worker_by_id", schema=_NODE_SCHEMAS["shutdown_worker_by_id"])
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

    @endpoint("shutdown_worker_by_port", schema=_NODE_SCHEMAS["shutdown_worker_by_port"])
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

    @endpoint("shutdown_all_workers", schema=_NODE_SCHEMAS["shutdown_all_workers"])
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

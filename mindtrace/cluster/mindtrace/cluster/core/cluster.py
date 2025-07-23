import multiprocessing
from abc import abstractmethod

import requests
from pydantic import BaseModel

from mindtrace.cluster.core import types as cluster_types
from mindtrace.core import TaskSchema
from mindtrace.database import BackendType, UnifiedMindtraceODMBackend
from mindtrace.jobs import Consumer, Job, JobSchema, Orchestrator, RabbitMQClient
from mindtrace.services import Gateway, Service


class ClusterManager(Gateway):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orchestrator = Orchestrator(backend=RabbitMQClient())
        self.redis_url = self.config["MINDTRACE_CLUSTER_DEFAULT_REDIS_URL"]
        self.job_schema_targeting_database = UnifiedMindtraceODMBackend(
            unified_model_cls=cluster_types.JobSchemaTargeting,
            redis_url=self.redis_url,
            preferred_backend=BackendType.REDIS
        )
        self.job_schema_targeting_database.initialize_sync()
        self.job_status_database = UnifiedMindtraceODMBackend(
            unified_model_cls=cluster_types.JobStatus,
            redis_url=self.redis_url,
            preferred_backend=BackendType.REDIS
        )
        self.job_status_database.initialize_sync()
        self.add_endpoint(
            "/submit_job", 
            func=self.submit_job, 
            schema=TaskSchema(
                name="submit_job", 
                input_schema=Job,
                output_schema=cluster_types.JobStatus
            ),
            methods=["POST"]
        )
        self.add_endpoint(
            "/register_job_to_endpoint",
            func=self.register_job_to_endpoint,
            schema=cluster_types.RegisterJobToEndpointTaskSchema(),
            methods=["POST"],
        )
        self.add_endpoint(
            "/register_job_to_worker",
            func=self.register_job_to_worker,
            schema=cluster_types.RegisterJobToWorkerTaskSchema,
            methods=["POST"],
        )
        self.add_endpoint(
            "/get_job_status",
            func=self.get_job_status,
            schema=cluster_types.GetJobStatusTaskSchema,
            methods=["POST"],
        )
        self.add_endpoint(
            "/worker_alert_started_job",
            func=self.worker_alert_started_job,
            schema=cluster_types.WorkerAlertStartedJobTaskSchema,
            methods=["POST"],
        )   
        self.add_endpoint(
            "/worker_alert_completed_job",
            func=self.worker_alert_completed_job,
            schema=cluster_types.WorkerAlertCompletedJobTaskSchema,
            methods=["POST"],
        )

    def register_job_to_endpoint(self, payload: cluster_types.RegisterJobToEndpointInput):
        """
        Register a job to an endpoint.

        Args:
            payload (RegisterJobToEndpointInput): The payload containing the job type and endpoint.
        """
        for entry in self.job_schema_targeting_database.find(self.job_schema_targeting_database.redis_backend.model_cls.schema_name == payload.job_type):
            self.logger.info(f"Deleting old job schema targeting for job type {payload.job_type} from endpoint {entry.target_endpoint}")
            self.job_schema_targeting_database.delete(entry.pk)
        self.job_schema_targeting_database.insert(cluster_types.JobSchemaTargeting(
            schema_name=payload.job_type,
            target_endpoint=payload.endpoint
        ))
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
            job_id=job.id,
            status="running",
            output={},
            worker_id=endpoint
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

        job_status.status = result.get("status", "completed")
        job_status.output = result.get("output", {})
        self.job_status_database.insert(job_status)
        self.logger.info(f"Completed job {job.id} with status {job_status.status}")
        return job_status

    def submit_job(self, job: Job):
        """
        Submit a job to the cluster. Will route to the appropriate endpoint based on the job type, or to the Orchestrator once that is implemented.

        Args:
            job (Job): The job to submit.

        Returns:
            JobOutput: The output of the job.
        """
        job_status = cluster_types.JobStatus(
            job_id=job.id,
            status="queued",
            output={},
            worker_id=""
        )
        self.job_status_database.insert(job_status)

        job_schema_targeting_list = self.job_schema_targeting_database.find(self.job_schema_targeting_database.redis_backend.model_cls.schema_name == job.schema_name)
        if not job_schema_targeting_list:
            self.logger.error(f"No job schema targeting found for job type {job.schema_name}")
            raise ValueError(f"No job schema targeting found for job type {job.schema_name}")
        job_schema_targeting = job_schema_targeting_list[0]
        if job_schema_targeting.target_endpoint == "@orchestrator":
            self.orchestrator.publish(job.schema_name, job)
            return job_status
        return self._submit_job_to_endpoint(job, job_schema_targeting.target_endpoint)

    def register_job_to_worker(self, payload: dict):
        """
        Register a job to a worker.

        Args:
            job_type (str): The type of job to register.
            worker_url (str): The URL of the worker to register the job to.
        """
        job_type = payload["job_type"]
        worker_url = payload["worker_url"]
        for entry in self.job_schema_targeting_database.find(self.job_schema_targeting_database.redis_backend.model_cls.schema_name == job_type):
            self.logger.info(f"Deleting old job schema targeting for job type {job_type} from endpoint {entry.target_endpoint}")
            self.job_schema_targeting_database.delete(entry.pk)
        self.job_schema_targeting_database.insert(cluster_types.JobSchemaTargeting(
            schema_name=job_type,
            target_endpoint="@orchestrator"
        ))
        self.orchestrator.register(JobSchema(name=job_type, input=BaseModel)) 
        worker_cm = Worker.connect(worker_url)  
        worker_cm.connect_to_cluster(
            backend_args=self.orchestrator.backend.consumer_backend_args, 
            queue_name=job_type,
            cluster_url=str(self._url)
        )
        self.logger.info(f"Connected {worker_url} to cluster {str(self._url)} listening on queue {job_type}")

    def get_job_status(self, payload: dict):
        """
        Get the status of a job. Does not query the worker, only the database.
        
        Args:
            payload (dict): The payload containing the job id. 

        Returns:
            JobStatus: The status of the job.
        """
        job_id = payload["job_id"]
        job_status_list = self.job_status_database.find(self.job_status_database.redis_backend.model_cls.job_id == job_id)
        if not job_status_list:
            raise ValueError(f"Job status not found for job id {job_id}")
        return job_status_list[0]

    def worker_alert_started_job(self, payload: dict):  
        """
        Alert the cluster manager that a job has started.

        Args:
            payload (dict): The payload containing the job id and the worker id that started the job.
        """
        job_id = payload["job_id"]  
        job_status_list = self.job_status_database.find(self.job_status_database.redis_backend.model_cls.job_id == job_id)
        if not job_status_list:
            raise ValueError(f"Job status not found for job id {job_id}")
        job_status = job_status_list[0]
        job_status.status = "running"
        job_status.worker_id = payload["worker_id"]
        self.job_status_database.insert(job_status)
        self.logger.info(f"Worker {payload['worker_id']} alerted cluster manager that job {job_id} has started")

    def worker_alert_completed_job(self, payload: dict):
        """
        Alert the cluster manager that a job has completed.

        Args:
            payload (dict): The payload containing the job id and the output of the job.
        """
        job_id = payload["job_id"]
        self.logger.info(f"Worker {payload['worker_id']} alerted cluster manager that job {job_id} has completed")
        job_status_list = self.job_status_database.find(self.job_status_database.redis_backend.model_cls.job_id == job_id)
        if not job_status_list:
            raise ValueError(f"Job status not found for job id {job_id}")
        job_status = job_status_list[0]
        if job_status.worker_id != payload["worker_id"]:
            self.logger.warning(f"Worker {payload['worker_id']} alerted cluster manager that job {job_id} has completed, but the worker id does not match the stored worker id {job_status.worker_id}")
        job_status.status = payload["status"]
        job_status.output = payload["output"]
        self.job_status_database.insert(job_status)
        
class Worker(Service, Consumer):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.add_endpoint("/start", self.start, schema=TaskSchema(name="start_worker"))
        self.add_endpoint("/run", self.run, schema=cluster_types.WorkerRunTaskSchema)
        self.add_endpoint("/connect_to_cluster", self.connect_to_cluster, schema=cluster_types.ConnectToBackendTaskSchema)
        self.consume_process = None
        self._cluster_connection_manager = None # type: ignore
        self._cluster_url = None

    @property
    def cluster_connection_manager(self):
        if self._cluster_connection_manager is None and self._cluster_url is not None:
            self._cluster_connection_manager = ClusterManager.connect(self._cluster_url)
        return self._cluster_connection_manager

    def run(self, job_dict: dict):
        cm = self.cluster_connection_manager
        if cm:
            cm.worker_alert_started_job(job_id=job_dict["id"], worker_id=str(self.id))
        else:
            self.logger.warning(f"No cluster connection manager found for worker {self.id}")
        output = self._run(job_dict["payload"])
        if cm:
            cm.worker_alert_completed_job(job_id=job_dict["id"], worker_id=str(self.id), status=output["status"], output=output["output"])
        else:
            self.logger.warning(f"No cluster connection manager found for worker {self.id}")
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
        raise NotImplementedError("Subclasses must implement this method") # pragma: no cover
    
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
        self.consume_process = multiprocessing.Process(target=self.consume)
        self.consume_process.start()
        self.logger.info(f"Worker {self.id} started consuming from queue {queue_name}, process id {self.consume_process.pid}")
        
    def shutdown(self):
        """
        If the consume process is running, we need to kill it too when the worker is shutdown.
        """
        if self.consume_process is not None:
            self.consume_process.kill()
            self.logger.info(f"Worker {self.id} killed consume process {self.consume_process.pid} as part of shutdown")
        return super().shutdown() 

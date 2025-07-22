import requests

from mindtrace.cluster.core import types as cluster_types
from mindtrace.jobs import Job
from mindtrace.registry import Registry
from mindtrace.services import Gateway


class ClusterManager(Gateway):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._registry = Registry(self.config["MINDTRACE_CLUSTER_DEFAULT_REGISTRY_DIR"], version_objects=False)
        self._job_registry = {}
        self._registry.save("jobregistry", self._job_registry)
        self.add_endpoint(
            "/submit_job", func=self.submit_job, schema=cluster_types.SubmitJobTaskSchema(), methods=["POST"]
        )
        self.add_endpoint(
            "/register_job_to_endpoint",
            func=self.register_job_to_endpoint,
            schema=cluster_types.RegisterJobToEndpointTaskSchema(),
            methods=["POST"],
        )

    def register_job_to_endpoint(self, payload: cluster_types.RegisterJobToEndpointInput):
        """
        Register a job to an endpoint.

        Args:
            payload (RegisterJobToEndpointInput): The payload containing the job type and endpoint.
        """
        self._job_registry[payload.job_type] = payload.endpoint
        self._registry.save("jobregistry", self._job_registry)

    def _submit_job_to_endpoint(self, job: Job):
        """
        Submit a job to the appropriate endpoint.

        Args:
            job (Job): The job to submit.

        Returns:
            JobOutput: The output of the job.
        """
        endpoint_url = f"{self._url}{self._job_registry[job.schema_name]}"
        print(endpoint_url)
        response = requests.post(endpoint_url, json=job.payload, timeout=60)

        if response.status_code != 200:
            raise RuntimeError(f"Gateway proxy request failed: {response.text}")

        # Parse response
        try:
            result = response.json()
        except Exception:
            result = {}

        return cluster_types.JobOutput(status="success", output=result)

    def submit_job(self, job: Job):
        """
        Submit a job to the cluster. Will route to the appropriate endpoint based on the job type, or to the Orchestrator once that is implemented.

        Args:
            job (Job): The job to submit.

        Returns:
            JobOutput: The output of the job.
        """
        if job.schema_name in self._job_registry:
            return self._submit_job_to_endpoint(job)
        else:
            self._job_registry = self._registry.load("jobregistry")
            if job.schema_name in self._job_registry:
                return self._submit_job_to_endpoint(job)
            else:
                return cluster_types.JobOutput(status="failed", output={})

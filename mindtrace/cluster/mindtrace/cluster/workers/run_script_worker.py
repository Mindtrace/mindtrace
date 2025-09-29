import os

from pydantic import BaseModel

from mindtrace.cluster import Worker
from mindtrace.cluster.workers.environments.docker_env import DockerEnvironment
from mindtrace.cluster.workers.environments.git_env import GitEnvironment


class RunScriptWorker(Worker):
    def __init__(self, *, devices=None, **kwargs):
        super().__init__(**kwargs)
        self.devices = devices if devices else []

    """Worker that creates a fresh environment for each job.

    Each job gets its own isolated environment based on the job message configuration. The environment is cleaned up
    after each job completes execution.
    """

    def start(self):
        super().start()
        self.working_dir = None
        self.container_id = None
        self.env_manager = None

    def setup_environment(self, environment_config: dict):
        """Setup environment based on job configuration."""
        # TODO: add devices
        if environment_config.get("git"):
            self.env_manager = GitEnvironment(
                repo_url=environment_config["git"]["repo_url"],
                branch=environment_config["git"].get("branch"),
                commit=environment_config["git"].get("commit"),
                working_dir=environment_config["git"].get("working_dir"),
            )
            self.working_dir = self.env_manager.setup()  # This handles dependency syncing

        elif environment_config.get("docker"):
            volumes = environment_config["docker"].get("volumes", {})
            # this is not a good way to handle this, but it's a quick fix for now
            if "GCP_CREDENTIALS" in volumes:
                volumes[os.environ["GOOGLE_APPLICATION_CREDENTIALS"]] = volumes["GCP_CREDENTIALS"]
                volumes.pop("GCP_CREDENTIALS")
            self.env_manager = DockerEnvironment(
                image=environment_config["docker"]["image"],
                working_dir=environment_config["docker"].get("working_dir"),
                environment=environment_config["docker"].get("environment", {}),
                volumes=volumes,
                devices=self.devices,
            )
            self.container_id = self.env_manager.setup()
        else:
            raise ValueError(
                "No valid environment configuration in job data. Make sure to specify either 'git' or 'docker' in the job data."
            )

    def _run(self, job_dict: dict) -> dict:
        """Execute a job in a fresh environment."""
        try:
            # Setup environment based on job configuration
            self.setup_environment(job_dict["environment"])
            exit_code, stdout, stderr = self.env_manager.execute(job_dict["command"])
            if exit_code != 0:
                return {"status": "failed", "output": {"stdout": stdout, "stderr": stderr}}
            return {"status": "completed", "output": {"stdout": stdout, "stderr": stderr}}
        except Exception as e:
            self.logger.error(f"Error executing job: {e}")
            raise e
        finally:
            self.cleanup_environment()

    def cleanup_environment(self):
        """Cleanup environment."""
        if self.env_manager:
            self.env_manager.cleanup()
            self.env_manager = None
        self.working_dir = None
        self.container_id = None

    def prepare_devices(self):
        """Prepare the environment for script execution based on the devices specified in the job configuration.

        Currently, limits GPU usage to the specified devices.
        """
        if not self.devices or self.devices == "cpu":
            visible_devices = None
            local_devices = "cpu"
        elif self.devices == "auto":
            local_devices = "auto"
            visible_devices = ""
        else:
            visible_devices = ",".join(map(str, self.devices))
            local_devices = ",".join(map(str, range(len(self.devices))))
        return visible_devices, local_devices


class RunScriptWorkerInput(BaseModel):
    environment: dict
    command: str


class RunScriptWorkerOutput(BaseModel):
    output: str
    error: str

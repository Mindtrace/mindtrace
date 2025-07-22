import os
import uuid

from mindtrace.cluster import Worker
from mindtrace.cluster.workers.environments.git_env import GitEnvironment
from mindtrace.cluster.workers.environments.docker_env import DockerEnvironment
from mindtrace.jobs import JobSchema
from pydantic import BaseModel

class RunScriptWorker(Worker):
    """Worker that creates a fresh environment for each job.

    Each job gets its own isolated environment based on the job message configuration. The environment is cleaned up
    after each job completes execution.
    """
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
            print(volumes)
            if "GCP_CREDENTIALS" in volumes:
                volumes[os.environ["GOOGLE_APPLICATION_CREDENTIALS"]] = volumes["GCP_CREDENTIALS"]
                volumes.pop("GCP_CREDENTIALS")
            print(volumes)
            self.env_manager = DockerEnvironment(
                image=environment_config["docker"]["image"],
                working_dir=environment_config["docker"].get("working_dir"),
                environment=environment_config["docker"].get("environment", {}),
                volumes=volumes,
                # devices=self.devices,
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
            self.setup_environment(job_dict.get("environment"))
            exit_code, stdout, stderr = self.env_manager.execute(
                job_dict.get("command"),
            )
            if exit_code != 0:
                return {"status": "failed", "output": {"stdout": stdout, "stderr": stderr}}
            return {"status": "completed", "output": {"stdout": stdout, "stderr": stderr}}

            if job_dict.get("environment", {}).get("git"):
                script = job_dict.get("environment", {}).get("git", {}).get("entry_point")
                if not script:
                    raise ValueError("No script specified in job data")

                args = job_dict.get("args", {})

                # Environment variables for the script
                visible_devices, local_devices = self.prepare_devices()

                env = {
                    **os.environ,
                    "PYTHONPATH": self.working_dir if isinstance(self.env_manager, GitEnvironment) else "/app",
                    **{f"ARG_{k.upper()}": str(v) for k, v in args.items()},
                    "CUDA_VISIBLE_DEVICES": visible_devices
                    if visible_devices != ""
                    else os.environ.get("CUDA_VISIBLE_DEVICES", ""),
                    "DEVICES": local_devices,
                    "JOB_ID": job_dict.get("job_id", uuid.uuid4().__str__()),
                }

                exit_code, stdout, stderr = self.env_manager.execute(
                    ["uv", "run", script], env=env, cwd=self.working_dir
                )

                if exit_code != 0:
                    raise RuntimeError(f"Script execution failed: {stderr}")

                return {"output": stdout, "error": stderr}
            elif job_dict.get("environment", {}).get("docker"):
                script = job_dict.get("environment", {}).get("docker", {}).get("entry_point")
                exit_code, stdout, stderr = self.env_manager.execute(
                    script,
                )
                print(stdout)
                if exit_code != 0:
                    raise RuntimeError(f"Script execution failed: {stderr}")

                return {"output": stdout, "error": stderr}
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

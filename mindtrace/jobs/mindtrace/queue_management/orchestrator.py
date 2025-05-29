from .base.orchestrator_backend import OrchestratorBackend

class Orchestrator:
    def __init__(self, _backend: OrchestratorBackend) -> None:
        self._backend = _backend

    def publish(self, job: Job):
        self._backend.publish(queue_name, message)

    def register(self, job: JobSchema):
        pass

    def _poll_worker(self, worker_id: str):
        pass

    def restart_job(self, job_id: str):
        pass

    
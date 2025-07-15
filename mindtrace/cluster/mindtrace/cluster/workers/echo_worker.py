import time

from mindtrace.cluster.core.cluster import Worker
from mindtrace.services.sample.echo_service import EchoInput, EchoOutput


class EchoWorker(Worker):

    def _run(self, job_dict: dict) -> dict:
        if job_dict.get("delay", 0) > 0:
            time.sleep(job_dict["delay"])
        print(job_dict["message"])
        return {"output": job_dict["message"]}
import time

from mindtrace.cluster.core.worker import Worker
from mindtrace.services.sample.echo_service import EchoInput, EchoOutput


class EchoWorker(Worker):

    def run(self, job_dict: dict) -> dict:
        job_dict = job_dict["payload"]
        if job_dict.get("delay", 0) > 0:
            time.sleep(job_dict["delay"])
        print(job_dict["message"])
        return {"status": "success", "output": job_dict["message"]}
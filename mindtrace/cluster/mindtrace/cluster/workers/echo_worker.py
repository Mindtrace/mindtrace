import time

from mindtrace.cluster.core.cluster import Worker


class EchoWorker(Worker):
    def _run(self, job_dict: dict) -> dict:
        if job_dict.get("delay", 0) > 0:
            time.sleep(job_dict["delay"])
        print(job_dict["message"])
        return {"status": "completed", "output": {"echoed": job_dict["message"]}}

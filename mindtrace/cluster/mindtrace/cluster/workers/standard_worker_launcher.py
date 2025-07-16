import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from mindtrace.core import get_class
from mindtrace.registry import Archiver
from mindtrace.services import ConnectionManager


class ProxyWorker(BaseModel):
    worker_type: str
    worker_params: dict


class StandardWorkerLauncher(Archiver):
    """This class saves a ProxyWorker to a file, which contains the class name and parameters of the worker.
    When loaded, it will launch the worker and return a ConnectionManager object.
    """

    def __init__(self, uri: str, *args, **kwargs):
        super().__init__(uri=uri, *args, **kwargs)

    def save(self, data: ProxyWorker):
        with open(Path(self.uri) / "worker.json", "w") as f:
            json.dump(data.model_dump(), f)

    def load(self, data_type: Any, url: str) -> ConnectionManager:
        with open(Path(self.uri) / "worker.json", "r") as f:
            worker_dict = json.load(f)
        worker_class = get_class(worker_dict["worker_type"])
        print(url)
        return worker_class.launch(url=url, **worker_dict["worker_params"], wait_for_launch=True, timeout=60)

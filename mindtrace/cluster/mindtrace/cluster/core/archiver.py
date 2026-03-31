import json
from pathlib import Path
from typing import Any

import requests
from fastapi import HTTPException

from mindtrace.cluster.core import types as cluster_types
from mindtrace.cluster.workers.environments.git_env import GitEnvironment
from mindtrace.core import Timeout, get_class
from mindtrace.registry import Archiver
from mindtrace.services import ConnectionManager


class StandardWorkerLauncher(Archiver):
    """This class saves a ProxyWorker to a file, which contains the class name and parameters of the worker.
    When loaded, it will launch the worker and return a ConnectionManager object.
    """

    def __init__(self, uri: str, *args, **kwargs):
        super().__init__(uri=uri, *args, **kwargs)

    def save(self, data: cluster_types.ProxyWorker):
        with open(Path(self.uri) / "worker.json", "w") as f:
            json.dump(data.model_dump(), f)

    def load(self, data_type: Any, url: str) -> ConnectionManager:
        from mindtrace.cluster.core.worker import Worker

        with open(Path(self.uri) / "worker.json", "r") as f:
            worker_dict = json.load(f)
        if worker_dict["git_repo_url"]:
            environment = GitEnvironment(
                repo_url=worker_dict["git_repo_url"],
                branch=worker_dict["git_branch"],
                commit=worker_dict["git_commit"],
                working_dir=worker_dict["git_working_dir"],
                project=worker_dict.get("git_project"),
                depth=worker_dict.get("git_depth"),
            )
            _ = environment.setup()

            # All kwargs (including URL params) go directly to init_params
            init_params = {"url": str(url), **worker_dict["worker_params"]}

            # Strip the URL of the http:// or https:// prefix
            if url.startswith("http://"):
                url_stripped = url[len("http://") :]
            elif url.startswith("https://"):
                url_stripped = url[len("https://") :]
            else:
                url_stripped = url

            # Create launch command
            launch_command = [
                "python",
                "-m",
                "mindtrace.services.core.launcher",
                "-s",
                worker_dict["worker_type"],
                "-w",
                "1",
                "-b",
                url_stripped,
                "-k",
                "uvicorn.workers.UvicornWorker",
                "--init-params",
                json.dumps(init_params),
            ]
            pid = environment.execute(launch_command, detach=True)
            self.logger.info(f"Worker {worker_dict['worker_type']} launched on url {url} with pid {pid}")
            timeout_handler = Timeout(
                timeout=60,
                exceptions=(ConnectionRefusedError, requests.exceptions.ConnectionError, HTTPException),
                desc=f"Launching {worker_dict['worker_type']} at {url}",
            )
            try:
                connection_manager = timeout_handler.run(Worker.connect, url=url)
            except Exception as e:
                self.logger.error(f"Failed to connect to worker {worker_dict['worker_type']} at {url}: {e}")
                raise e
            return connection_manager
        else:
            worker_class = get_class(worker_dict["worker_type"])
            return worker_class.launch(url=url, **worker_dict["worker_params"], wait_for_launch=True, timeout=60)

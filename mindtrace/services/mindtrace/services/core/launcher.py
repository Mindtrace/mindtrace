import argparse
import json
import logging
import platform
from argparse import RawTextHelpFormatter
from pathlib import Path

from mindtrace.core import instantiate_target, setup_logger

# Platform-specific imports
IS_WINDOWS = platform.system() == "Windows"
if not IS_WINDOWS:
    from gunicorn.app.base import BaseApplication


if not IS_WINDOWS:

    class Launcher(BaseApplication):
        """Gunicorn application launcher for Mindtrace services (Linux/Mac only)."""

        def __init__(self, options):
            self.gunicorn_options = {
                "bind": options.bind,
                "workers": options.num_workers,
                "worker_class": options.worker_class,
                "pidfile": options.pid,
            }

            # Parse init params
            init_params = json.loads(options.init_params) if options.init_params else {}

            # Create server with initialization parameters
            server = instantiate_target(options.server_class, pid_file=options.pid, **init_params)
            server.logger = setup_logger(
                name=server.unique_name,
                stream_level=logging.INFO,
                file_level=logging.DEBUG,
                log_dir=Path(server.config["MINDTRACE_DIR_PATHS"]["LOGGER_DIR"]),
            )
            self.application = server.app
            server.url = options.bind
            super().__init__()

        def load_config(self):
            config = {
                key: value
                for key, value in self.gunicorn_options.items()
                if key in self.cfg.settings and value is not None
            }
            for key, value in config.items():
                self.cfg.set(key.lower(), value)

        def load(self):
            return self.application
else:

    class Launcher:
        """Uvicorn application launcher for Mindtrace services (Windows)."""

        def __init__(self, options):
            # Parse init params
            init_params = json.loads(options.init_params) if options.init_params else {}

            # Create server with initialization parameters
            server = instantiate_target(options.server_class, pid_file=options.pid, **init_params)
            server.logger = setup_logger(
                name=server.unique_name,
                stream_level=logging.INFO,
                file_level=logging.DEBUG,
                log_dir=Path(server.config["MINDTRACE_DIR_PATHS"]["LOGGER_DIR"]),
            )
            self.application = server.app

            # Parse bind address
            host, port = options.bind.split(":")

            # Store uvicorn config
            self.uvicorn_config = {
                "app": self.application,
                "host": host,
                "port": int(port),
                "workers": options.num_workers,
            }

        def run(self):
            import uvicorn

            uvicorn.run(**self.uvicorn_config)


def main():
    parser = argparse.ArgumentParser(description="MINDTRACE SERVER LAUNCHER\n", formatter_class=RawTextHelpFormatter)
    parser.add_argument(
        "-s",
        "--server_class",
        type=str,
        nargs="?",
        default="mindtrace.services.core.serve.Service",
        help="Server class to launch",
    )
    parser.add_argument("-w", "--num_workers", type=int, default=1, help="Number of workers")
    parser.add_argument(
        "-b", "--bind", type=str, default="127.0.0.1:8080", help="URL address to bind with the application"
    )
    parser.add_argument("-p", "--pid", type=str, default=None)
    parser.add_argument("-k", "--worker_class", type=str, default="uvicorn.workers.UvicornWorker")
    parser.add_argument("--init-params", type=str, help="JSON string of initialization parameters")
    args = parser.parse_args()

    Launcher(args).run()


if __name__ == "__main__":
    main()

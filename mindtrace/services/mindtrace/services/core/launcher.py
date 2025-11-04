import argparse
import json
from argparse import RawTextHelpFormatter

from gunicorn.app.base import BaseApplication

from mindtrace.core import instantiate_target


class Launcher(BaseApplication):
    """Gunicorn application launcher for Mindtrace services."""

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
        server = instantiate_target(options.server_class, **init_params)
        self.application = server.app
        server.url = options.bind
        super().__init__()

    def load_config(self):
        config = {
            key: value for key, value in self.gunicorn_options.items() if key in self.cfg.settings and value is not None
        }
        for key, value in config.items():
            self.cfg.set(key.lower(), value)

    def load(self):
        return self.application


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

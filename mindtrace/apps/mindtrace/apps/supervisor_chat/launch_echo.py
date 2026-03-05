import os
from mindtrace.services.samples.echo_service import EchoService

HOST = "localhost"
PORT = 8080


if __name__ == "__main__":
    EchoService.launch(host=HOST, port=PORT, block=True)

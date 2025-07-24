import os
import reflex as rx
import socket
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(dotenv_path=Path(".env"))

def find_free_port(start_port=3000, max_tries=50):
    for port in range(start_port, start_port + max_tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("", port))
                return port
            except OSError:
                continue
    raise RuntimeError("No free ports found.")

frontend_port = int(os.getenv("FRONTEND_PORT", find_free_port(3000)))
backend_port = int(os.getenv("BACKEND_PORT", find_free_port(8000)))

class PoseidonConfig(rx.Config):
    pass

config = PoseidonConfig(
    app_name="poseidon",
    db_url="sqlite:///poseidon.db",
    env=rx.Env.DEV,
    frontend_port=frontend_port,
    backend_port=backend_port,
)

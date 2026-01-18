#!/usr/bin/env python3
"""
Launch script for Authenticated CRUD Service.

Run this script to start the authenticated CRUD service and access Swagger documentation.

This script automatically starts MongoDB in a Docker container if not already running,
and stops it when the script exits.

Prerequisites:
- Docker installed and running
- Environment variables override defaults if needed:
  - MONGO_URI: Full MongoDB connection string
  - MONGO_USERNAME, MONGO_PASSWORD: For authentication
  - MONGO_DB_NAME: Database name
- JWT_SECRET environment variable (optional, defaults to a test secret)

The MongoDB URI is configured in the code (auth_crud_service.py) and can be overridden
via environment variables. Database is created on demand.
"""

import atexit
import os
import subprocess
import sys
import time
from urllib.parse import quote_plus

from auth_crud_service import AuthenticatedCRUDService

# MongoDB Docker container configuration
MONGO_CONTAINER_NAME = "auth_crud_mongo"
MONGO_IMAGE = "mongo:7"
MONGO_PORT = "27017"
MONGO_ROOT_USERNAME = "admin"
MONGO_ROOT_PASSWORD = "adminpassword"
MONGO_DB_NAME = "auth_crud_db"


def is_mongo_running(container_name: str = MONGO_CONTAINER_NAME) -> bool:
    """Check if MongoDB container is running.

    Args:
        container_name: Name of the MongoDB container

    Returns:
        True if container is running, False otherwise
    """
    try:
        check_result = subprocess.run(
            ["docker", "ps", "--filter", f"name={container_name}", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            check=False,
        )
        return container_name in check_result.stdout
    except (subprocess.SubprocessError, FileNotFoundError):
        return False


def start_mongo_container(
    container_name: str = MONGO_CONTAINER_NAME,
    image: str = MONGO_IMAGE,
    port: str = MONGO_PORT,
    root_username: str = MONGO_ROOT_USERNAME,
    root_password: str = MONGO_ROOT_PASSWORD,
    db_name: str = MONGO_DB_NAME,
) -> bool:
    """Start MongoDB in a Docker container.

    Args:
        container_name: Name for the container
        image: MongoDB Docker image to use
        port: Port to expose MongoDB on
        root_username: Root username for MongoDB
        root_password: Root password for MongoDB
        db_name: Initial database name

    Returns:
        True if container started successfully, False otherwise
    """
    # Check if container already exists
    try:
        check_result = subprocess.run(
            ["docker", "ps", "-a", "--filter", f"name={container_name}", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            check=False,
        )
        container_exists = container_name in check_result.stdout

        if container_exists:
            # Container exists, try to start it
            print(f"Starting existing MongoDB container '{container_name}'...")
            subprocess.run(
                ["docker", "start", container_name],
                check=False,
            )
        else:
            # Create and start new container
            print(f"Creating and starting MongoDB container '{container_name}'...")
            subprocess.run(
                [
                    "docker",
                    "run",
                    "-d",
                    "--name",
                    container_name,
                    "-p",
                    f"{port}:27017",
                    "-e",
                    f"MONGO_INITDB_ROOT_USERNAME={root_username}",
                    "-e",
                    f"MONGO_INITDB_ROOT_PASSWORD={root_password}",
                    "-e",
                    f"MONGO_INITDB_DATABASE={db_name}",
                    image,
                ],
                check=False,
            )

        # Wait for MongoDB to be ready
        print("Waiting for MongoDB to be ready...")
        max_attempts = 30
        for _ in range(max_attempts):
            if is_mongo_running(container_name):
                # Try to connect to verify it's ready
                try:
                    ping_result = subprocess.run(
                        [
                            "docker",
                            "exec",
                            container_name,
                            "mongosh",
                            "--eval",
                            "db.adminCommand('ping')",
                            "--quiet",
                        ],
                        capture_output=True,
                        check=False,
                        timeout=5,
                    )
                    if ping_result.returncode == 0:
                        print("MongoDB is ready!")
                        return True
                except (subprocess.TimeoutExpired, subprocess.SubprocessError):
                    pass
            time.sleep(1)

        print("Warning: MongoDB container started but may not be fully ready")
        return True
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        print(f"Error starting MongoDB container: {e}")
        return False


def stop_mongo_container(container_name: str = MONGO_CONTAINER_NAME) -> None:
    """Stop MongoDB Docker container.

    Args:
        container_name: Name of the container to stop
    """
    try:
        if is_mongo_running(container_name):
            print(f"\nStopping MongoDB container '{container_name}'...")
            subprocess.run(
                ["docker", "stop", container_name],
                check=False,
            )
            print("MongoDB container stopped.")
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        print(f"Error stopping MongoDB container: {e}")


def build_mongo_uri() -> str | None:
    """Build MongoDB URI from environment variables or return None to use default.

    Supports:
    - MONGO_URI: Full MongoDB connection string
    - Individual components: MONGO_USERNAME, MONGO_PASSWORD, MONGO_HOST, MONGO_PORT, MONGO_AUTH_SOURCE

    Returns:
        MongoDB connection URI string or None to use service default
    """
    # If full URI is provided, use it
    provided_uri = os.getenv("MONGO_URI")
    if provided_uri:
        return provided_uri

    # Build URI from components if credentials are provided
    mongo_host = os.getenv("MONGO_HOST")
    mongo_port = os.getenv("MONGO_PORT")
    mongo_username = os.getenv("MONGO_USERNAME")
    mongo_password = os.getenv("MONGO_PASSWORD")
    mongo_auth_source = os.getenv("MONGO_AUTH_SOURCE", "admin")

    # If any component is provided, build URI (otherwise use service default)
    if mongo_host or mongo_port or mongo_username or mongo_password:
        mongo_host = mongo_host or "localhost"
        mongo_port = mongo_port or "27017"

        # If credentials are provided, build authenticated URI
        if mongo_username and mongo_password:
            # URL encode username and password to handle special characters
            encoded_username = quote_plus(mongo_username)
            encoded_password = quote_plus(mongo_password)
            return f"mongodb://{encoded_username}:{encoded_password}@{mongo_host}:{mongo_port}/?authSource={mongo_auth_source}"

        # Build URI without authentication
        return f"mongodb://{mongo_host}:{mongo_port}"

    # Return None to use service default
    return None


if __name__ == "__main__":
    print("=" * 60)
    print("Starting Authenticated CRUD Service")
    print("=" * 60)

    # Check if MongoDB is already running (might be external instance)
    mongo_started_by_script = False
    if not is_mongo_running(MONGO_CONTAINER_NAME):
        # Check if MongoDB is accessible on the port (might be external instance)
        try:
            import socket

            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            port_check = sock.connect_ex(("localhost", int(MONGO_PORT)))
            sock.close()
            if port_check != 0:
                # Port is not accessible, start our container
                mongo_started_by_script = start_mongo_container()
                if not mongo_started_by_script:
                    print("Warning: Failed to start MongoDB container. Continuing anyway...")
        except (socket.error, OSError, ValueError) as e:
            print(f"Warning: Could not check MongoDB port: {e}")
    else:
        print(f"MongoDB container '{MONGO_CONTAINER_NAME}' is already running.")

    # Register cleanup function to stop MongoDB on exit
    if mongo_started_by_script:
        atexit.register(stop_mongo_container, MONGO_CONTAINER_NAME)

        # Also handle Ctrl+C gracefully
        def signal_handler(_sig, _frame):
            stop_mongo_container(MONGO_CONTAINER_NAME)
            sys.exit(0)

        import signal

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    # Get MongoDB configuration (None uses service defaults)
    mongo_uri = build_mongo_uri()
    mongo_db_name = os.getenv("MONGO_DB_NAME")

    # Display configuration
    if mongo_uri:
        # Mask password in display
        display_uri = mongo_uri
        if "@" in display_uri and ":" in display_uri.split("@")[0]:
            # Mask password in URI for display
            parts = display_uri.split("@")
            if len(parts) == 2:
                auth_part = parts[0].split("://")[1] if "://" in parts[0] else parts[0]
                if ":" in auth_part:
                    display_uri = display_uri.replace(f":{auth_part.split(':')[1]}", ":****")
        print(f"\nMongoDB URI: {display_uri}")
    else:
        print(f"\nMongoDB URI: {AuthenticatedCRUDService.DEFAULT_MONGO_URI} (default)")

    if mongo_db_name:
        print(f"MongoDB Database: {mongo_db_name}")
    else:
        print(f"MongoDB Database: {AuthenticatedCRUDService.DEFAULT_MONGO_DB_NAME} (default)")

    print("\nService will be available at: http://localhost:8080")
    print("Swagger UI: http://localhost:8080/docs")
    print("ReDoc: http://localhost:8080/redoc")
    print("\nNote: Authenticated endpoints require a Bearer token")
    print("Use generate_token.py to create test tokens")
    print("\nPress Ctrl+C to stop the service")
    print("=" * 60 + "\n")

    # Prepare launch kwargs (only include if not None to use defaults)
    launch_kwargs = {
        "host": "0.0.0.0",  # Listen on all interfaces
        "port": 8080,
        "wait_for_launch": True,
        "block": True,  # Keep service running
        "timeout": 30,
        "progress_bar": False,  # Disable progress bar for cleaner output
    }

    # Only add MongoDB config if provided (otherwise use service defaults)
    if mongo_uri:
        launch_kwargs["mongo_uri"] = mongo_uri
    if mongo_db_name:
        launch_kwargs["mongo_db_name"] = mongo_db_name

    # Launch service in blocking mode
    AuthenticatedCRUDService.launch(**launch_kwargs)

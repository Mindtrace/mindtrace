#!/usr/bin/env python3
"""
Gateway Service example showing how to:
1. Launch a Gateway service
2. Register other services with the Gateway
3. Make requests through the Gateway to registered services
4. Use ProxyConnectionManager for transparent service routing
"""

from mindtrace.services.sample.echo_service import EchoInput, EchoOutput

from mindtrace.cluster import ClusterManager
from mindtrace.cluster.workers.echo_worker import EchoWorker
from mindtrace.jobs import JobSchema, job_from_schema

echo_job = JobSchema(name="echo_job", input=EchoInput, output=EchoOutput)


def base_gateway_example():
    """Example demonstrating the ProxyConnectionManager functionality."""
    print("\nStarting ProxyConnectionManager example...")

    # Launch Gateway service on port 8097
    cluster_cm = ClusterManager.launch(port=8097, wait_for_launch=True, timeout=15)
    print("Gateway launched successfully!")

    # Launch EchoService on port 8098
    echo_cm = EchoWorker.launch(port=8098, wait_for_launch=True, timeout=15)
    print("EchoService launched successfully!")

    try:
        # Register the EchoService with the Gateway INCLUDING the connection manager
        # This enables the ProxyConnectionManager functionality
        result = cluster_cm.register_app(
            name="echo",
            url="http://localhost:8098/",
            connection_manager=echo_cm,  # Provide the connection manager to the Gateway to enable ProxyConnectionManager functionality
        )
        print(f"EchoService registered with Gateway: {result}")
        print(f"Registered apps: {cluster_cm.registered_apps}")

        cluster_cm.register_job_to_endpoint(job_type="echo_job", endpoint="echo/run")
        print(job_from_schema(echo_job, EchoInput(message="echo")).model_dump())
        result = cluster_cm.submit_job(job_from_schema(echo_job, EchoInput(message="echo")))

        print("Job submitted")
        print(result)

    finally:
        # Clean up in reverse order
        echo_cm.shutdown()
        cluster_cm.clear_databases()
        cluster_cm.shutdown()
        print("Services shut down successfully!")


if __name__ == "__main__":
    # Run sync example
    base_gateway_example()

    print("\nAll Cluster as Gateway examples completed!")

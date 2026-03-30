import os

from mindtrace.cluster import ClusterManager, Node

if __name__ == "__main__":
    os.environ["MINDTRACE_CLUSTER__MINIO_HOST"] = "localhost"
    os.environ["MINDTRACE_CLUSTER__MINIO_PORT"] = "9100"
    os.environ["MINDTRACE_CLUSTER__MINIO_ACCESS_KEY"] = "minioadmin"
    os.environ["MINDTRACE_CLUSTER__MINIO_SECRET_KEY"] = "minioadmin"

    os.environ["MINDTRACE_WORKER__DEFAULT_REDIS_URL"] = "redis://localhost:6380"
    os.environ["MINDTRACE_CLUSTER__DEFAULT_REDIS_URL"] = "redis://localhost:6380"
    os.environ["MINDTRACE_CLUSTER__RABBITMQ_PORT"] = "5673"
    os.environ["MINDTRACE_CLUSTER__WORKER_PORTS_RANGE"] = "8200-8202"
    os.environ["REDIS_OM_URL"] = "redis://localhost:6380"

    cluster_url = "http://localhost:8502"
    node_url = "http://localhost:8503"
    cluster_manager = ClusterManager.launch(url=cluster_url, wait_for_launch=True)
    node = Node.launch(cluster_url=cluster_url, url=node_url, block=True)

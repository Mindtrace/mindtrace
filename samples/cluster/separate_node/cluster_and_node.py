from mindtrace.cluster import ClusterManager, Node

if __name__ == "__main__":
    cluster_url = "http://localhost:8002"
    node_url = "http://localhost:8003"
    cluster_manager = ClusterManager.launch(url=cluster_url, wait_for_launch=True)
    node = Node.launch(cluster_url=cluster_url, url=node_url, block=True)

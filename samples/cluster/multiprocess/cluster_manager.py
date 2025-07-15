from mindtrace.cluster import ClusterManager

if __name__ == "__main__":
    cluster_manager = ClusterManager.launch(host="localhost", port=8000, block=True)

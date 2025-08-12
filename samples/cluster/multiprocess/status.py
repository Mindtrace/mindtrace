import time

from mindtrace.cluster import ClusterManager

if __name__ == "__main__":
    cluster_manager = ClusterManager.connect("http://localhost:8002")
    while True:
        time.sleep(1)
        print(cluster_manager.get_job_status(job_id="0c8fca72-4eff-4adc-81fc-0cb18740b0f5"))

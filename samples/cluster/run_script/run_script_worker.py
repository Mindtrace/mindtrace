import time

from mindtrace.cluster import ClusterManager, Node
from mindtrace.cluster.workers.run_script_worker import RunScriptWorkerInput, RunScriptWorkerOutput
from mindtrace.jobs import JobSchema, job_from_schema


def main():
    cluster_manager = ClusterManager.launch(host="localhost", port=8000, wait_for_launch=True)
    node = Node.launch(
        host="localhost", port=8001, cluster_url=str(cluster_manager.url), wait_for_launch=True, timeout=15
    )
    try:
        sample_vbrain_schema = JobSchema(
            name="sample_vbrain",
            input=RunScriptWorkerInput,
            output=RunScriptWorkerOutput,
        )
        cluster_manager.register_worker_type(
            worker_name="runscriptworker",
            worker_class="mindtrace.cluster.workers.run_script_worker.RunScriptWorker",
            worker_params={},
            job_type="sample_vbrain",
        )
        worker_url = "http://localhost:8002"
        cluster_manager.launch_worker(node_url=str(node.url), worker_type="runscriptworker", worker_url=worker_url)
        job = job_from_schema(
            sample_vbrain_schema,
            input_data={
                "environment": {
                    "git": {
                        "repo_url": "https://github.com/Mindtrace/mindtrace.git",
                        "branch": "feature/cluster/git-and-docker",
                        "working_dir": "",
                    }
                },
                "command": "python samples/cluster/run_script/test_script.py",
            },
        )

        cluster_manager.submit_job(job)
        status = cluster_manager.get_job_status(job_id=job.id)
        while status.status != "completed" and status.status != "failed":
            print(status)
            time.sleep(1)
            status = cluster_manager.get_job_status(job_id=job.id)
        print(status)
    finally:
        node.shutdown()
        cluster_manager.clear_databases()
        cluster_manager.shutdown()


if __name__ == "__main__":
    main()

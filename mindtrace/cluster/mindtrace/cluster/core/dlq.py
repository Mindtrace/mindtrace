from pprint import pprint as pp

def process_dlq(cluster_manager):
    jobs = cluster_manager.get_dlq_jobs().jobs
    requeue_jobs = []
    for job in jobs:
        pp(job)
        todo = input("What to do? ([r]equeue/[d]iscard/[s]kip/[q]uit): ")
        if todo == "r":
            requeue_jobs.append(cluster_manager.requeue_from_dlq(job_id=job.job_id))
        elif todo == "d":
            cluster_manager.discard_from_dlq(job_id=job.job_id)
        elif todo == "s":
            continue
        elif todo == "q":
            break
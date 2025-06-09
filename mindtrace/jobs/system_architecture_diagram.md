# System Architecture: Job Management with Cluster Integration

## System Overview

```mermaid
graph TB
    User[User] --> Cluster[Cluster]
    User --> JobManager[Job Manager]
    
    Cluster --> Orchestrator[Orchestrator]
    Cluster --> Workers[Workers]
    
    JobManager --> Storage[Storage]
    
    Orchestrator --> Workers
    Workers --> JobManager
```

## Detailed Flow

```mermaid
flowchart LR
    A[User] --> B[cluster.submit]
    B --> C[Cluster]
    C --> D[spawn Worker]
    C --> E[Job Manager register]
    D --> F[execute job]
    F --> G[update status]
    G --> E
```

## Sequence Diagram

```mermaid
sequenceDiagram
    User->>Cluster: submit job
    Cluster->>JobManager: register job
    Cluster->>Worker: spawn/route job
    Worker->>Worker: execute
    Worker->>JobManager: update status
    JobManager->>Storage: persist data
```

## Component Types

```mermaid
graph TB
    subgraph Workers
        DW[Dynamic Workers]
        SW[Static Workers]
    end
    
    subgraph Backends
        L[Local]
        R[Redis] 
        RM[RabbitMQ]
    end
    
    Orchestrator --> Backends
    Cluster --> Workers
```

## Key Benefits

- **Job History & Analytics**: Track all jobs across worker types
- **Failed Job Recovery**: Identify and restart failed jobs
- **System Monitoring**: Queue statistics and performance metrics
- **Bulk Operations**: Mass actions on multiple jobs
- **Clean Architecture**: Cluster handles execution, Job Manager handles lifecycle

## Example Usage

```python
# Setup
cluster = Cluster.connect()
job_manager = JobManager(orchestrator)

# Submit and track job
cluster_job_id = cluster.submit(job)
job_manager.register_job(mgr_id, job_def, cluster_job_id)

# Monitor and manage
failed_jobs = job_manager.list_jobs(ExecutionStatus.FAILED)
job_manager.restart_job(failed_job_id)
```
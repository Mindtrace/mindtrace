#!/usr/bin/env python3
"""
Example usage of the Job Management System
Shows job lifecycle management and various queue operations
"""

from mindtrace.jobs import Job, JobSchema, ExecutionStatus, LocalClient, RedisClient, Orchestrator


def main():
    print("=== Job Management System - Complete Workflow ===\n")
    
    # Setup with local backend for demonstration
    backend = LocalClient()
    orchestrator = Orchestrator(backend)
    
    print("1. Job Creation and Schema Definition:")
    print()
    
    # Create different types of job schemas
    ml_schema = JobSchema(
        name="machine_learning_training",
        input={
            "dataset_path": "/data/training.csv",
            "model_type": "xgboost",
            "hyperparameters": {"n_estimators": 100, "max_depth": 6}
        },
        config={
            "timeout": 3600,
            "memory_limit": "8GB",
            "gpu_required": True
        },
        metadata={
            "team": "ml",
            "priority": "high",
            "cost_center": "research"
        }
    )
    
    data_processing_schema = JobSchema(
        name="data_processing",
        input={
            "source_file": "/raw/data.parquet",
            "transformations": ["normalize", "feature_engineer"],
            "output_format": "csv"
        },
        config={
            "timeout": 1800,
            "memory_limit": "4GB"
        }
    )
    
    # Create job instances
    ml_job = Job(
        id="ml_job_001",
        job_schema=ml_schema,
        created_at="2024-01-01T10:00:00"
    )
    
    data_job = Job(
        id="data_job_001", 
        job_schema=data_processing_schema,
        created_at="2024-01-01T10:05:00"
    )
    
    print(f"✓ Created ML job: {ml_job.job_schema.name}")
    print(f"✓ Created Data job: {data_job.job_schema.name}")
    print()
    
    print("2. Queue Management and Job Distribution:")
    print()
    
    # Declare different queue types
    backend.declare_queue("jobs.ml", queue_type="priority")
    backend.declare_queue("jobs.data", queue_type="fifo")
    backend.declare_queue("jobs.urgent", queue_type="stack")
    
    # Publish jobs to appropriate queues
    orchestrator.publish("jobs.ml", ml_job, priority=10)  # High priority
    orchestrator.publish("jobs.data", data_job)
    
    print("✓ Published jobs to queues")
    print(f"✓ ML queue size: {orchestrator.count_queue_messages('jobs.ml')}")
    print(f"✓ Data queue size: {orchestrator.count_queue_messages('jobs.data')}")
    print()
    
    print("3. Job Processing Simulation:")
    print()
    
    # Simulate worker receiving and processing jobs
    received_ml_job = orchestrator.receive_message("jobs.ml")
    if received_ml_job:
        print(f"✓ Worker received ML job: {received_ml_job.id}")
        
        # Simulate job status updates
        received_ml_job.status = ExecutionStatus.RUNNING
        received_ml_job.started_at = "2024-01-01T10:10:00"
        print(f"✓ Job status updated to: {received_ml_job.status}")
        
        # Simulate completion
        received_ml_job.status = ExecutionStatus.COMPLETED
        received_ml_job.completed_at = "2024-01-01T11:10:00"
        received_ml_job.job_schema.output = {
            "model_path": "/models/xgboost_001.pkl",
            "accuracy": 0.95,
            "training_time": 3600
        }
        print(f"✓ Job completed with output: {received_ml_job.job_schema.output}")
    
    print()
    
    print("4. Backend Switching Example:")
    print()
    
    print("# Switch to Redis for production")
    print("# redis_backend = RedisClient(host='redis-server', port=6379)")
    print("# orchestrator = Orchestrator(redis_backend)")
    print()
    print("# Same API, distributed queues!")
    print("# orchestrator.publish('jobs.ml', ml_job)")
    print()
    
    print("5. Job Monitoring and Management:")
    print()
    
    # Queue monitoring
    remaining_jobs = orchestrator.count_queue_messages("jobs.data")
    print(f"✓ Remaining data jobs: {remaining_jobs}")
    
    # Cleanup operations
    if remaining_jobs > 0:
        print("✓ Processing remaining jobs...")
        data_job_received = orchestrator.receive_message("jobs.data")
        if data_job_received:
            print(f"✓ Processed: {data_job_received.id}")
    
    # Queue cleanup
    orchestrator.clean_queue("jobs.ml")
    orchestrator.clean_queue("jobs.data") 
    print("✓ Queues cleaned")
    print()
    
    print("6. Error Handling Example:")
    print()
    
    # Create a job that might fail
    error_schema = JobSchema(
        name="error_prone_task",
        input={"data": "invalid"}
    )
    error_job = Job(
        id="error_job_001",
        job_schema=error_schema,
        created_at="2024-01-01T12:00:00"
    )
    
    # Simulate error handling
    error_job.status = ExecutionStatus.FAILED
    error_job.error = "Invalid input data format"
    error_job.completed_at = "2024-01-01T12:01:00"
    
    print(f"✓ Job failed: {error_job.error}")
    print(f"✓ Final status: {error_job.status}")
    print()
    
    print("=== Job Management System Demo Complete ===")


if __name__ == "__main__":
    main() 
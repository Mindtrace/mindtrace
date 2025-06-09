#!/usr/bin/env python3
"""
Example usage of the Orchestrator component
Shows the core message queue and routing functionality
"""

from mindtrace.jobs import Job, JobSchema, Orchestrator, LocalClient


def main():
    print("=== Orchestrator - Message Queue and Routing System ===\n")
    
    # Setup orchestrator with local backend
    backend = LocalClient()
    orchestrator = Orchestrator(backend)
    
    print("1. Basic queue operations:")
    print()
    
    # Create sample jobs
    vbrain_schema = JobSchema(
        name="vbrain",
        input={"entry_point": "main.py", "args": "--dataset data.csv"}
    )
    vbrain_job = Job(
        id="vbrain_001",
        job_schema=vbrain_schema,
        created_at="2024-01-01T00:00:00"
    )
    
    detection_schema = JobSchema(
        name="detection", 
        input={"image_paths": ["/path/to/img1.jpg", "/path/to/img2.jpg"]}
    )
    detection_job = Job(
        id="detection_001",
        job_schema=detection_schema,
        created_at="2024-01-01T00:00:00"
    )
    
    # Declare queues first
    backend.declare_queue("jobs.vbrain")
    backend.declare_queue("jobs.detection")
    
    # Publish jobs to different queues
    print("Publishing jobs to queues...")
    orchestrator.publish("jobs.vbrain", vbrain_job)
    orchestrator.publish("jobs.detection", detection_job)
    orchestrator.publish("jobs.vbrain", vbrain_job)  # Another vbrain job
    
    # Check queue sizes
    vbrain_count = orchestrator.count_queue_messages("jobs.vbrain")
    detection_count = orchestrator.count_queue_messages("jobs.detection")
    
    print(f"✓ VBrain queue: {vbrain_count} jobs")
    print(f"✓ Detection queue: {detection_count} jobs")
    print()
    
    print("2. Receiving jobs from queues:")
    print()
    
    # Receive jobs (like workers would)
    vbrain_received = orchestrator.receive_message("jobs.vbrain")
    detection_received = orchestrator.receive_message("jobs.detection")
    
    if vbrain_received:
        print(f"✓ Received VBrain job: {vbrain_received.job_schema.name}")
    
    if detection_received:
        print(f"✓ Received Detection job: {detection_received.job_schema.name}")
    
    # Check updated queue sizes
    vbrain_count = orchestrator.count_queue_messages("jobs.vbrain")
    detection_count = orchestrator.count_queue_messages("jobs.detection")
    
    print(f"✓ VBrain queue after receive: {vbrain_count} jobs")
    print(f"✓ Detection queue after receive: {detection_count} jobs")
    print()
    
    print("3. Queue management:")
    print()
    
    # Clean a queue
    orchestrator.clean_queue("jobs.vbrain")
    vbrain_count = orchestrator.count_queue_messages("jobs.vbrain")
    print(f"✓ VBrain queue after clean: {vbrain_count} jobs")
    print()
    
    print("4. Integration patterns (how external Cluster would use this):")
    print()
    print("# Cluster publishes jobs to orchestrator")
    print("orchestrator.publish('jobs.vbrain', job)")
    print("orchestrator.publish('jobs.detection', job)")
    print()
    print("# Workers receive jobs from orchestrator")
    print("job = orchestrator.receive_message('jobs.vbrain')")
    print("if job:")
    print("    # Process the job...")
    print("    pass")
    print()
    print("# Cluster monitors queue sizes")
    print("vbrain_backlog = orchestrator.count_queue_messages('jobs.vbrain')")
    print("if vbrain_backlog > 10:")
    print("    # Spawn more workers...")
    print("    pass")
    print()
    
    print("5. Backend flexibility:")
    print()
    print("# Switch to Redis backend")
    print("# from mindtrace.jobs import RedisClient")
    print("# redis_backend = RedisClient(host='localhost', port=6379)")
    print("# orchestrator = Orchestrator(redis_backend)")
    print("#")
    print("# Switch to RabbitMQ backend") 
    print("# from mindtrace.jobs import RabbitMQClient")
    print("# rabbitmq_backend = RabbitMQClient(host='localhost')")
    print("# orchestrator = Orchestrator(rabbitmq_backend)")
    print()
    print("Same Orchestrator API, different backend implementations!")


if __name__ == "__main__":
    main() 
# Mindtrace Jobs Module

A backend-agnostic job queue system with automatic queuing direction.
The jobs module is designed for integration with distributed systems through the Orchestrator interface. Applications can use the orchestrator to manage job queues and routing.

## Architecture 

## Core Components

### Job Structure

```python
from mindtrace.jobs import Job, JobSchema, JobInput, JobOutput
from mindtrace.jobs.mindtrace.types import JobType

class ClassificationInput(JobInput):
    model: str
    epochs: int
    batch_size: int = 32

class DetectionOutput(JobOutput):
    accuracy: float
    

# Create job schema
schema = JobSchema(
    name="Detection_inference",
    input=ClassificationInput(model="yolo:x", epochs=5),
    output=DetectionOutput
)

job = Job(
    id="job_123",
    name="classification_inference",
    job_type=JobType.CLASSIFICATION,
    payload=schema,
    priority=5
)
```
## Backend Support

### Local Backend (Development)
```python
from mindtrace.jobs import Orchestrator, LocalClient

# In-memory queues for testing
orchestrator = Orchestrator(LocalClient())
```

### Redis Backend
```python
from mindtrace.jobs import Orchestrator, RedisClient

orchestrator = Orchestrator(RedisClient(
    host="redis.cluster.local",
    port=6379
))
```

### RabbitMQ Backend
```python
from mindtrace.jobs import Orchestrator, RabbitMQClient

orchestrator = Orchestrator(RabbitMQClient(
    host="rabbitmq.cluster.local",
    port=5672,
    username="...",
    password="..."
))
```

## Usage Patterns

### Job Publishing
```python
job = Job(
    id="detection_001",
    name="object_detection",
    job_type=JobType.OBJECT_DETECTION,
    payload=DetectionSchema(
        input=DetectionInput(Datalake.dataset),
        output=None
    ),
    entrypoint="detect.py"
)

orchestrator.declare_queue("detection_jobs")
orchestrator.publish("detection_jobs", job)
```



### Queue Management
```python
# Monitor queue status
count = orchestrator.count_queue_messages("detection_jobs")
print(f"Pending jobs: {count}")

# Clean completed jobs
orchestrator.clean_queue("detection_jobs")
```

## Auto-Routing Logic

The system automatically determines routing based on:

1. **Job Type**: `job.job_type` maps to queue using `QUEUE_MAPPING` (e.g., `JobType.OBJECT_DETECTION` → `"detection_jobs"`)
2. **Payload Type**: Input class determines worker specialization
3. **Entrypoint**: Execution hint for worker processes
4. **Priority**: Optional processing order within queues

Available Job Types:
- `JobType.ML_TRAINING` → `"ml_training_jobs"`
- `JobType.OBJECT_DETECTION` → `"detection_jobs"`
- `JobType.DATA_PROCESSING` → `"data_jobs"`
- `JobType.CLASSIFICATION` → `"classification_jobs"`
- `JobType.DEFAULT` → `"default_jobs"`

## Testing

Run the full test suite:
```bash
python -m pytest tests/jobs/ -v
```

Coverage includes:
- Queue operations (declare, publish, receive, clean)
- Backend-specific functionality (Redis persistence, RabbitMQ exchanges)
- Orchestrator integration patterns
- Priority queue handling

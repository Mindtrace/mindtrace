# Mindtrace Jobs Module

A powerful, backend-agnostic job queue system designed for distributed computing with strong typing and automatic routing.

## Architecture Philosophy

The jobs module follows a **cluster-level routing** approach where:
- **Users** create jobs with minimal infrastructure knowledge
- **Cluster** automatically determines backend, queues, and routing
- **Workers** receive strongly-typed jobs from specialized queues

## Core Components

### Job Structure

```python
from mindtrace.jobs import Job, JobSchema, JobInput, JobOutput

# Define strongly-typed input/output models
class VBrainInput(JobInput):
    model_path: str
    epochs: int
    batch_size: int = 32

class VBrainOutput(JobOutput):
    accuracy: float
    model_url: str

# Create job schema
schema = JobSchema(
    name="vbrain_training",
    input=VBrainInput(model_path="/models/v1", epochs=100),
    output=None  # Set after completion
)

# Create job instance (system auto-routes)
job = Job(
    id="job_123",
    name="vbrain_training",
    payload=schema,
    entrypoint="train.py",
    priority=5
)
```

### Key Classes

- **`JobInput`**: Base class for strongly-typed job inputs
- **`JobOutput`**: Base class for strongly-typed job outputs  
- **`JobSchema`**: Container with name, input, and output
- **`Job`**: Execution-ready job with metadata and routing hints
- **`Orchestrator`**: Queue management and message routing
- **`LocalClient`**: In-memory backend for development
- **`RedisClient`**: Distributed backend with persistence
- **`RabbitMQClient`**: Enterprise backend with complex routing

## Backend Support

### Local Backend (Development)
```python
from mindtrace.jobs import Orchestrator, LocalClient

# In-memory queues for testing
orchestrator = Orchestrator(LocalClient())
```

### Redis Backend (Production)
```python
from mindtrace.jobs import Orchestrator, RedisClient

# Distributed workers with persistence
orchestrator = Orchestrator(RedisClient(
    host="redis.cluster.local",
    port=6379
))
```

### RabbitMQ Backend (Enterprise)
```python
from mindtrace.jobs import Orchestrator, RabbitMQClient

# Complex routing with exchanges
orchestrator = Orchestrator(RabbitMQClient(
    host="rabbitmq.cluster.local",
    port=5672,
    username="worker",
    password="secret"
))
```

## Usage Patterns

### Job Publishing
```python
# User creates job (no infrastructure knowledge needed)
job = Job(
    id="detection_001",
    name="object_detection",
    payload=DetectionSchema(
        input=DetectionInput(image_url="s3://bucket/image.jpg"),
        output=None
    ),
    entrypoint="detect.py"
)

# Cluster automatically routes to detection_jobs queue
orchestrator.publish_message("detection_jobs", job)
```

### Job Processing
```python
# Worker receives from specialized queue
job = orchestrator.receive_message("detection_jobs")
if job:
    # Execute with strongly-typed input
    result = process_detection(job.payload.input)
    
    # Update with typed output
    job.payload.output = DetectionOutput(
        objects=result.objects,
        confidence=result.confidence
    )
    job.status = ExecutionStatus.COMPLETED
```

### Queue Management
```python
# Declare queues
orchestrator.declare_queue("vbrain_jobs")
orchestrator.declare_queue("detection_jobs") 

# Monitor queue status
count = orchestrator.queue_status("vbrain_jobs")
print(f"Pending jobs: {count}")

# Clean completed jobs
orchestrator.clean_queue("vbrain_jobs")
```

## Auto-Routing Logic

The system automatically determines routing based on:

1. **Job Name**: `job.name` maps to queue (e.g., `"vbrain_training"` → `"vbrain_jobs"`)
2. **Payload Type**: Input class determines worker specialization
3. **Entrypoint**: Execution hint for worker processes
4. **Priority**: Optional processing order within queues

## Integration with Cluster

```python
# Cluster deployment pattern
class ClusterJobManager:
    def __init__(self, environment: str):
        if environment == "development":
            client = LocalClient()
        elif environment == "production": 
            client = RedisClient(host=os.getenv("REDIS_HOST"))
        else:  # enterprise
            client = RabbitMQClient(
                host=os.getenv("RABBITMQ_HOST"),
                username=os.getenv("RABBITMQ_USER"),
                password=os.getenv("RABBITMQ_PASS")
            )
        
        self.orchestrator = Orchestrator(client)
    
    def submit_job(self, job: Job) -> str:
        queue_name = self._determine_queue(job.name)
        self.orchestrator.publish_message(queue_name, job)
        return job.id
    
    def _determine_queue(self, job_name: str) -> str:
        # Auto-routing logic
        if "vbrain" in job_name:
            return "vbrain_jobs"
        elif "detection" in job_name:
            return "detection_jobs"
        else:
            return "default_jobs"
```

## Strong Typing Benefits

- **Compile-time validation** of job inputs/outputs
- **IDE autocompletion** for job data structures  
- **Runtime type checking** via Pydantic
- **Clear contracts** between job producers and consumers
- **Reduced errors** from malformed job data

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
- Error conditions and cleanup

## Migration from Legacy

The new structure eliminates infrastructure fields from Job:

**Before (Legacy)**:
```python
job = Job(
    job_schema=schema,
    backend_type="redis",     # Removed
    queue_name="vbrain_jobs", # Removed  
    routing_key="training"    # Removed
)
```

**After (Current)**:
```python
job = Job(
    payload=schema,           # Renamed from job_schema
    entrypoint="train.py"     # Added execution hint
    # System auto-determines backend/queue/routing
)
```

This provides a cleaner separation between user concerns (job definition) and infrastructure concerns (routing/backends). 
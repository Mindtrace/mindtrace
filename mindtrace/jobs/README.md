# Mindtrace Jobs Module

A backend-agnostic job queue system with automatic queuing direction.
The jobs module is designed for integration with distributed systems through the Orchestrator interface. Applications can use the orchestrator to manage job queues and routing.

## Core Concepts

### Job Structure
```python
from mindtrace.jobs import Job, JobSchema, JobInput, JobType

class SimpleJobInput(JobInput):
    data: str = "test_data"
    param1: str = "value1"

input_data = SimpleJobInput()
schema = JobSchema(name="example_schema", input=input_data)

job = Job(
    id="job_123",
    name="example_job",
    job_type=JobType.DATA_PROCESSING,
    payload=schema,
    created_at="2024-01-01T00:00:00"
)
```

### Job Types
- `JobType.ML_TRAINING` → `"ml_training_jobs"`
- `JobType.OBJECT_DETECTION` → `"detection_jobs"`
- `JobType.DATA_PROCESSING` → `"data_jobs"`
- `JobType.CLASSIFICATION` → `"classification_jobs"`
- `JobType.DEFAULT` → `"default_jobs"`

## Quick Start

```python
from mindtrace.jobs import Orchestrator, LocalClient

orchestrator = Orchestrator(LocalClient())
orchestrator.declare_queue("my_queue")
orchestrator.publish("my_queue", job)

received_job = orchestrator.receive_message("my_queue")
```

## Backend Support

### Local Backend 
```python
from mindtrace.jobs import LocalClient, Orchestrator

client = LocalClient(broker_id="my_app")
orchestrator = Orchestrator(client)
```

### Redis Backend 
```python
from mindtrace.jobs import RedisClient, Orchestrator

client = RedisClient(host="localhost", port=6379, db=0)
orchestrator = Orchestrator(client)
```

### RabbitMQ Backend 
```python
from mindtrace.jobs import RabbitMQClient, Orchestrator
import time

client = RabbitMQClient(
    host="localhost",
    port=5672,
    username="user",
    password="password"
)
orchestrator = Orchestrator(client)
```

## Queue Operations

### Basic Operations
```python
orchestrator.declare_queue("my_queue")
job_id = orchestrator.publish("my_queue", job)
received_job = orchestrator.receive_message("my_queue")
count = orchestrator.count_queue_messages("my_queue")
orchestrator.clean_queue("my_queue")
orchestrator.delete_queue("my_queue")
```

### Queue Types
```python
orchestrator.declare_queue("fifo_queue", queue_type="fifo")
orchestrator.declare_queue("stack_queue", queue_type="stack") 
orchestrator.declare_queue("priority_queue", queue_type="priority")
```

### Priority Queues
```python
orchestrator.publish("priority_queue", high_priority_job, priority=10)
orchestrator.publish("priority_queue", low_priority_job, priority=1)
```

### RabbitMQ Specific
```python
orchestrator.declare_queue("rabbitmq_queue", force=True)
orchestrator.declare_queue("priority_queue", force=True, max_priority=255)
orchestrator.publish("rabbitmq_queue", job)
time.sleep(0.1)  
count = orchestrator.count_queue_messages("rabbitmq_queue")
```

## Auto-Routing Logic

The system automatically determines routing based on:

1. **Job Type**: `job.job_type` maps to queue using `QUEUE_MAPPING`
2. **Queue Types**:
   - `"fifo"` - First in, first out (default)
   - `"stack"` - Last in, first out
   - `"priority"` - Priority-based ordering (Redis and RabbitMQ)

## Complete Example

```python
import time
from mindtrace.jobs import Orchestrator, RedisClient, Job, JobSchema, JobInput, JobType

class DataProcessingInput(JobInput):
    dataset_path: str
    processing_type: str
    timeout: int = 300

job_input = DataProcessingInput(
    dataset_path="/data/my_dataset.csv",
    processing_type="classification"
)

schema = JobSchema(name="data_processing_schema", input=job_input)

job = Job(
    id="dp_001",
    name="data_processing_job",
    job_type=JobType.DATA_PROCESSING,
    payload=schema,
    created_at="2024-01-01T00:00:00"
)

client = RedisClient(host="localhost", port=6379, db=0)
orchestrator = Orchestrator(client)

queue_name = "data_processing_queue"
orchestrator.declare_queue(queue_name)

job_id = orchestrator.publish(queue_name, job)
print(f"Published job: {job_id}")

count = orchestrator.count_queue_messages(queue_name)
print(f"Jobs in queue: {count}")

received_job = orchestrator.receive_message(queue_name)
if received_job:
    print(f"Processing job: {received_job.name}")
    
orchestrator.clean_queue(queue_name)
orchestrator.delete_queue(queue_name)
```

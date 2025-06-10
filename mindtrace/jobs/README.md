# Mindtrace Jobs Module

A backend-agnostic job queue system with automatic queuing direction.
The jobs module is designed for integration with distributed systems through the Orchestrator interface. Applications can use the orchestrator to manage job queues and routing.

## Architecture Overview

The Jobs module implements a consumer pattern with backend-specific optimizations:

**Key Architectural Benefits:**
- **Backend-Specific Optimizations**: Each backend has tailored consumer strategies
- **LocalConsumerBackend**: Fast in-memory operations, no polling delays
- **RedisConsumerBackend**: Blocking operations, timeout handling, connection management
- **RabbitMQConsumerBackend**: ACK/NACK support, prefetch control, delivery guarantees
- **Auto-Detection**: Consumer.connect() automatically selects the right backend
- **Unified API**: Same Consumer interface works across all backends
- **Mindtrace Integration**: All base classes inherit from Mindtrace/MindtraceABC

## Consumer Pattern

The Consumer class provides a simple API that automatically creates the appropriate backend-specific ConsumerBackend when connected to an Orchestrator:

1. **User Layer**: Your consumer classes inherit from Consumer and implement `run(job)`
2. **Abstraction Layer**: Consumer and Orchestrator provide unified APIs
3. **Backend-Specific Layer**: ConsumerBackend classes handle backend optimizations
4. **Backend Layer**: LocalClient, RedisClient, RabbitMQClient manage infrastructure
5. **Infrastructure**: In-Memory Queues, Redis Server, RabbitMQ Server

## Backend-Specific Features

### LocalConsumerBackend
- ✅ **Optimized polling**: No timeouts needed for in-memory operations
- ✅ **Fast processing**: Immediate queue access
- ✅ **Simple error handling**: Lightweight retry mechanisms

### RedisConsumerBackend  
- ✅ **Blocking operations**: Efficient Redis BLPOP-style operations
- ✅ **Timeout handling**: Configurable poll timeouts (default: 5s)
- ✅ **Connection management**: Redis-specific connection optimizations
- ✅ **Backoff strategies**: Redis-aware error handling

### RabbitMQConsumerBackend
- ✅ **Message acknowledgment**: ACK for success, NACK for failures
- ✅ **Prefetch control**: Configurable prefetch count (default: 1)
- ✅ **Delivery guarantees**: Ensures message processing reliability
- ✅ **Dead letter queues**: Failed messages can be routed to DLQ

## Running Examples

### Example 1: Local Backend (Always Available)
```python
from mindtrace.jobs import Orchestrator, LocalClient, Consumer, JobSchema, JobInput

local_backend = LocalClient()
orchestrator = Orchestrator(local_backend)

schema = JobSchema(name="my_jobs", input=MyJobInput(), output=MyJobOutput())
orchestrator.register(schema)

class MyConsumer(Consumer):
    def run(self, job):
        print(f"Processing job {job.id} with LOCAL backend")

consumer = MyConsumer("my_jobs")
consumer.connect(orchestrator)
consumer.consume(num_messages=5)
```

### Example 2: Redis Backend (Requires Redis Server)
```python
from mindtrace.jobs import RedisClient

redis_backend = RedisClient(host="localhost", port=6379, db=0)
orchestrator = Orchestrator(redis_backend)

consumer = MyConsumer("my_jobs")
consumer.connect(orchestrator)
consumer.consume(num_messages=5)
```

### Example 3: RabbitMQ Backend (Requires RabbitMQ Server)
```python
from mindtrace.jobs import RabbitMQClient

rabbitmq_backend = RabbitMQClient(
    host="localhost", 
    port=5672, 
    username="user", 
    password="password"
)
orchestrator = Orchestrator(rabbitmq_backend)

consumer = MyConsumer("my_jobs")
consumer.connect(orchestrator)
consumer.consume(num_messages=5)
```

### Example 4: Multi-Backend Testing
```python
def test_all_backends():
    backends = [
        ("Local", LocalClient()),
        ("Redis", RedisClient(host="localhost", port=6379, db=0)),
        ("RabbitMQ", RabbitMQClient(host="localhost", port=5672, username="user", password="password"))
    ]
    
    for name, backend in backends:
        try:
            orchestrator = Orchestrator(backend)
            orchestrator.register(schema)
            
            consumer = MyConsumer("my_jobs")
            consumer.connect(orchestrator)
            print(f"✓ {name} backend: {type(consumer.consumer_backend).__name__}")
            
            consumer.consume(num_messages=1)
        except Exception as e:
            print(f"✗ {name} backend failed: {e}")

test_all_backends()
```

## Running the Complete Demo

```bash
python3 example_new_consumer.py
```

Expected output:
- ✓ Local: success - Created LocalConsumerBackend
- ✓ Redis: success - Created RedisConsumerBackend  
- ✓ RabbitMQ: success - Created RabbitMQConsumerBackend

## API Reference

### Consumer Class
```python
class Consumer(MindtraceABC):
    def __init__(self, job_type_name: str)
    def connect(self, orchestrator: Orchestrator) -> None
    def consume(self, num_messages: Optional[int] = None) -> None
    def run(self, job: Job) -> None  # Abstract method to implement
```

### Orchestrator Class
```python
class Orchestrator(Mindtrace):
    def __init__(self, backend: OrchestratorBackend)
    def register(self, schema: JobSchema) -> str
    def publish(self, queue_name: str, job: Job) -> str
    def receive_message(self, queue_name: str) -> Optional[Job]
    def count_queue_messages(self, queue_name: str) -> int
```

### JobSchema and Utilities
```python
class JobSchema:
    name: str
    input: JobInput
    output: JobOutput

def job_from_schema(schema: JobSchema, input_data: JobInput) -> Job
```

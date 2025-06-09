# Mindtrace Jobs Tests

This directory contains comprehensive tests for the Mindtrace Jobs queue management system.

## Test Structure

- `test_queue_backends.py` - Tests for all queue backends (Local, Redis, RabbitMQ)
- `conftest.py` - Pytest configuration and fixtures

## Prerequisites

### Required Services
The tests assume that Redis and RabbitMQ services are running locally:

```bash
# Start Redis (default port 6379)
redis-server

# Start RabbitMQ (default port 5672, web UI on 15672)
rabbitmq-server
```

### Python Dependencies
```bash
pip install pytest redis pika
```

## Running Tests

### Run All Tests
```bash
pytest tests/jobs/
```

### Run Specific Test Categories
```bash
# Only local broker tests (no external dependencies)
pytest -m "not redis and not rabbitmq" tests/jobs/

# Only Redis tests
pytest -m redis tests/jobs/

# Only RabbitMQ tests  
pytest -m rabbitmq tests/jobs/

# Only integration tests
pytest -m integration tests/jobs/
```

### Run with Different Verbosity
```bash
# Detailed output
pytest -v tests/jobs/

# Very detailed output
pytest -vv tests/jobs/

# Quiet mode
pytest -q tests/jobs/
```

## Test Coverage

### Backend Tests (`test_queue_backends.py`)
- ✅ **LocalBroker**: In-memory queue operations
- ✅ **RedisClient**: Redis-backed queues with real Redis server
- ✅ **RabbitMQClient**: RabbitMQ-backed queues with real RabbitMQ server
- ✅ **Orchestrator**: Abstraction layer over all backends

### Operations Tested
- Queue declaration (FIFO, Stack, Priority)
- Message publishing and receiving
- Queue counting and cleaning
- Queue deletion
- Priority queue ordering (Redis, RabbitMQ)
- Exchange operations (RabbitMQ)
- Cross-backend compatibility via Orchestrator

## Test Features

### No Mocking
Tests use real Redis and RabbitMQ instances - no mocking of external services. This provides:
- Real integration testing
- Actual network and serialization validation
- Performance characteristics of real systems

### Unique Test Data
Each test uses timestamp-based unique queue names to avoid conflicts:
```python
queue_name = f"test_queue_{int(time.time())}"
```

### Automatic Cleanup
Tests clean up queues and connections after execution.

### Markers
Tests are marked for easy filtering:
- `@pytest.mark.redis` - Requires Redis
- `@pytest.mark.rabbitmq` - Requires RabbitMQ  
- `@pytest.mark.integration` - Cross-system tests

## Example Usage

```python
from mindtrace.jobs import Job, JobSchema
from mindtrace.jobs.mindtrace.queue_management.local import LocalBroker
from mindtrace.jobs.mindtrace.queue_management.redis import RedisClient
from mindtrace.jobs.mindtrace.queue_management.rabbitmq import RabbitMQClient
from mindtrace.jobs.mindtrace.queue_management.orchestrator import Orchestrator

# Create a job schema
schema = JobSchema(
    name="data_processing",
    input={"file": "data.csv"},
    config={"timeout": 300}
)

# Create a job instance
job = Job(
    id="job_123",
    job_schema=schema,
    created_at="2025-01-06T12:00:00Z"
)

# Test with any backend
# Local (no external deps)
broker = LocalBroker()
orchestrator = Orchestrator(broker)

# Redis (requires redis-server)
client = RedisClient()
orchestrator = Orchestrator(client)

# RabbitMQ (requires rabbitmq-server)
client = RabbitMQClient()
orchestrator = Orchestrator(client)
```

## Troubleshooting

### Redis Connection Errors
```
redis.exceptions.ConnectionError: Error 111 connecting to localhost:6379
```
**Solution**: Start Redis server: `redis-server`

### RabbitMQ Connection Errors
```
pika.exceptions.AMQPConnectionError
```
**Solution**: Start RabbitMQ server: `rabbitmq-server`

### Import Errors
Make sure you're running from the project root and the mindtrace package is in your Python path. 
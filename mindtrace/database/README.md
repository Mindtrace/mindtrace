# Mindtrace Database Module

This module provides a flexible Object-Document Mapping (ODM) system for various database backends in the Mindtrace project.

## Features

- Multiple database backend support (MongoDB, Redis)
- Async/sync operation support
- Pydantic model integration
- Document-based operations
- Aggregation pipeline support (MongoDB)
- Exception handling for common database operations

## Available Backends

### 1. MongoMindtraceODMBackend
The primary backend using MongoDB with Beanie ODM.

### 2. RedisODMBackend
Redis-based backend for caching and fast key-value operations.

### 3. LocalODMBackend
Local storage backend for testing and development.

## Quick Start

### Step 1: Define Your Document Model
```python
from mindtrace.database.backends.mongo_odm_backend import MindtraceDocument

class MyDoc(MindtraceDocument):
    name: str
    value: int
    
    class Settings:
        use_cache = False
```

### Step 2: Initialize and Use Backend
```python
from mindtrace.database.backends.mongo_odm_backend import MongoMindtraceODMBackend

# Initialize backend
backend = MongoMindtraceODMBackend(
    model_cls=MyDoc,
    db_uri="mongodb://localhost:27017",
    db_name="mydb"
)

# Insert document
doc = await backend.insert(MyDoc(name="example", value=42))

# Get document by ID
retrieved_doc = await backend.get(doc.id)

# Get all documents
all_docs = await backend.all()

# Find documents with specific criteria
results = await backend.find({"name": "example"})

# Delete document
await backend.delete(doc.id)
```

## Available Methods

### Core Methods
- `insert(obj: BaseModel) -> ModelType`: Insert a new document
- `get(id: str) -> ModelType`: Retrieve document by ID
- `delete(id: str)`: Delete document by ID
- `all() -> List[ModelType]`: Retrieve all documents
- `find(*args, **kwargs)`: Find documents matching criteria

### MongoDB-Specific Methods
- `aggregate(pipeline: list)`: Run MongoDB aggregation pipeline
- `get_raw_model()`: Get the underlying document model class

## Exception Handling

The module provides two main exception types:

```python
from mindtrace.database.core.exceptions import DocumentNotFoundError, DuplicateInsertError

try:
    doc = await backend.get("non_existent_id")
except DocumentNotFoundError:
    print("Document not found")

try:
    doc = await backend.insert(duplicate_doc)
except DuplicateInsertError:
    print("Document already exists")
```

## Backend Configuration

### MongoDB Backend
```python
MongoMindtraceODMBackend(
    model_cls: Type[ModelType],  # Your document model class
    db_uri: str,                 # MongoDB connection URI
    db_name: str                 # Database name
)
```

### Redis Backend
```python
RedisODMBackend(
    model_cls: Type[ModelType],  # Your document model class
    redis_url: str               # Redis connection URL
)
```

### Local Backend
```python
LocalODMBackend(
    model_cls: Type[ModelType]   # Your document model class
)
```

## Best Practices

1. Always handle database exceptions appropriately
2. Use type hints with your models
3. Initialize backend connections at application startup
4. Use appropriate indices for better query performance

## Testing

### Setup Test Environment

The test suite uses Docker to run a MongoDB instance. To set up the test environment:

```bash
cd tests
docker compose up -d
```

### Running Tests

To run the test suite:

```bash
pytest tests/
```

### Test Coverage

The test suite covers:

1. **CRUD Operations**
   - Document creation with validation
   - Retrieval by ID
   - Document deletion
   - Listing all documents

2. **Query Operations**
   - Find with filters
   - Complex queries with multiple conditions
   - Aggregation pipelines
   - Pagination (skip/limit)
   - Projections

3. **Edge Cases**
   - Duplicate key handling
   - Invalid queries
   - Invalid aggregation pipelines
   - Multiple backend initialization

### Test Structure

The test suite uses pytest fixtures for setup and teardown:

- `event_loop`: Creates an event loop for async tests
- `mongo_client`: Provides MongoDB client instance
- `test_db`: Creates and cleans up test database
- `mongo_backend`: Sets up ODM backend with test models

Example test model:

```python
class UserDoc(MindtraceDocument):
    name: str
    age: int
    email: Annotated[str, Indexed(unique=True)]

    class Settings:
        name = "users"
        use_cache = False
```

### Writing New Tests

To add new tests:

1. Create test models inheriting from `MindtraceDocument`
2. Use the `@pytest.mark.asyncio` decorator for async tests
3. Use the `mongo_backend` fixture with your model:
   ```python
   @pytest.mark.parametrize("mongo_backend", [YourModel], indirect=True)
   async def test_your_feature(mongo_backend):
       # Your test code here
   ```

### Cleanup

To stop the test MongoDB instance:

```bash
cd tests
docker-compose down -v
```


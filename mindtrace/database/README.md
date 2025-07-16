# Mindtrace Database Module

A powerful, flexible Object-Document Mapping (ODM) system that provides a **unified interface** for working with multiple database backends in the Mindtrace project. Write once, run on MongoDB, Redis, or both!

## ✨ Key Features

- **Unified Backend System** - One interface for multiple databases
- **Dynamic Backend Switching** - Switch between MongoDB and Redis at runtime
- **Simplified Document Models** - Define once, use everywhere
- **Async/Sync Support** - Choose your preferred programming style
- **Advanced Querying** - Rich query capabilities across all backends
- **Comprehensive Error Handling** - Clear, actionable error messages
- **Full Test Coverage** - Thoroughly tested with unit and integration tests

## Quick Start

### The Simple Way: Unified Documents

Define your document model once and use it with any backend:

```python
from mindtrace.database import UnifiedMindtraceDocument, UnifiedMindtraceODMBackend, BackendType
from pydantic import Field

# 1. Define your document model (works with both MongoDB and Redis!)
class User(UnifiedMindtraceDocument):
    name: str = Field(description="User's full name")
    age: int = Field(ge=0, description="User's age")
    email: str = Field(description="User's email address")
    skills: list[str] = Field(default_factory=list)
    
    class Meta:
        collection_name = "users"
        global_key_prefix = "myapp"
        indexed_fields = ["email", "name"]
        unique_fields = ["email"]

# 2. Create backend (supports both MongoDB and Redis)
backend = UnifiedMindtraceODMBackend(
    unified_model_cls=User,
    mongo_db_uri="mongodb://localhost:27017",
    mongo_db_name="myapp",
    redis_url="redis://localhost:6379",
    preferred_backend=BackendType.MONGO  # Start with MongoDB
)

# 3. Initialize
await backend.initialize_async()  # For async operations
# or
backend.initialize_sync()  # For sync operations

# 4. Use it! (Same API regardless of backend)
user = User(name="Alice", age=30, email="alice@example.com", skills=["Python"])

# Insert
inserted_user = await backend.insert_async(user)
# or: inserted_user = backend.insert(user)

# Get by ID
retrieved_user = await backend.get_async(inserted_user.id)

# Find with filters
python_users = await backend.find_async({"skills": "Python"})

# Switch backends on the fly!
backend.switch_backend(BackendType.REDIS)
redis_user = backend.insert(user)  # Now using Redis

# Get all users
all_users = await backend.all_async()
```

### Traditional Way: Backend-Specific Models

If you prefer more control, you can still define backend-specific models:

```python
from mindtrace.database import (
    MongoMindtraceODMBackend, 
    RedisMindtraceODMBackend,
    MindtraceDocument,
    MindtraceRedisDocument
)
from beanie import Indexed
from redis_om import Field as RedisField
from typing import Annotated

# MongoDB model
class MongoUser(MindtraceDocument):
    name: str
    email: Annotated[str, Indexed(unique=True)]
    age: int
    
    class Settings:
        name = "users"

# Redis model
class RedisUser(MindtraceRedisDocument):
    name: str = RedisField(index=True)
    email: str = RedisField(index=True)
    age: int = RedisField(index=True)
    
    class Meta:
        global_key_prefix = "myapp"

# Use them separately
mongo_backend = MongoMindtraceODMBackend(
    model_cls=MongoUser,
    db_uri="mongodb://localhost:27017",
    db_name="myapp"
)

redis_backend = RedisMindtraceODMBackend(
    model_cls=RedisUser,
    redis_url="redis://localhost:6379"
)
```

## Available Backends

### 1. UnifiedMindtraceODMBackend (Recommended)

The flagship backend that provides a unified interface for multiple databases:

**Key Features:**
- **Single Interface**: One API for all backends
- **Runtime Switching**: Change backends without code changes
- **Automatic Model Generation**: Converts unified models to backend-specific formats
- **Flexible Configuration**: Use one or multiple backends

**Configuration Options:**
```python
# Option 1: Unified model (recommended)
backend = UnifiedMindtraceODMBackend(
    unified_model_cls=MyUnifiedDoc,
    mongo_db_uri="mongodb://localhost:27017",
    mongo_db_name="mydb",
    redis_url="redis://localhost:6379",
    preferred_backend=BackendType.MONGO
)

# Option 2: Separate models
backend = UnifiedMindtraceODMBackend(
    mongo_model_cls=MyMongoDoc,
    redis_model_cls=MyRedisDoc,
    mongo_db_uri="mongodb://localhost:27017",
    mongo_db_name="mydb",
    redis_url="redis://localhost:6379",
    preferred_backend=BackendType.REDIS
)

# Option 3: Single backend
backend = UnifiedMindtraceODMBackend(
    unified_model_cls=MyUnifiedDoc,
    mongo_db_uri="mongodb://localhost:27017",
    mongo_db_name="mydb",
    preferred_backend=BackendType.MONGO
)
```

### 2. MongoMindtraceODMBackend

Specialized MongoDB backend using Beanie ODM:

```python
from mindtrace.database import MongoMindtraceODMBackend, MindtraceDocument

class User(MindtraceDocument):
    name: str
    email: str
    
    class Settings:
        name = "users"
        use_cache = False

backend = MongoMindtraceODMBackend(
    model_cls=User,
    db_uri="mongodb://localhost:27017",
    db_name="myapp"
)

# Supports MongoDB-specific features
pipeline = [{"$match": {"age": {"$gte": 18}}}]
results = await backend.aggregate(pipeline)
```

### 3. RedisMindtraceODMBackend

High-performance Redis backend with JSON support:

```python
from mindtrace.database import RedisMindtraceODMBackend, MindtraceRedisDocument
from redis_om import Field

class User(MindtraceRedisDocument):
    name: str = Field(index=True)
    email: str = Field(index=True)
    age: int = Field(index=True)
    
    class Meta:
        global_key_prefix = "myapp"

backend = RedisMindtraceODMBackend(
    model_cls=User,
    redis_url="redis://localhost:6379"
)

# Initialize Redis OM
await backend.initialize()

# Supports Redis-specific queries
users = backend.find(User.age >= 18)
```

### 4. LocalMindtraceODMBackend

In-memory backend for testing and development:

```python
from mindtrace.database import LocalMindtraceODMBackend
from pydantic import BaseModel

class User(BaseModel):
    name: str
    email: str

backend = LocalMindtraceODMBackend(model_cls=User)
# No initialization needed - works immediately!
```

## API Reference

### Core Operations

All backends support these essential operations:

```python
# Insert a document
inserted_doc = await backend.insert_async(doc)
# or: inserted_doc = backend.insert(doc)

# Get document by ID
doc = await backend.get_async("doc_id")
# or: doc = backend.get("doc_id")

# Delete document
await backend.delete_async("doc_id")
# or: backend.delete("doc_id")

# Get all documents
all_docs = await backend.all_async()
# or: all_docs = backend.all()

# Find documents with filters
results = await backend.find_async({"name": "Alice"})
# or: results = backend.find({"name": "Alice"})
```

### Unified Backend Specific

Additional methods for the unified backend:

```python
# Backend management
backend.switch_backend(BackendType.REDIS)
current_type = backend.get_current_backend_type()
is_async = backend.is_async()

# Backend availability
has_mongo = backend.has_mongo_backend()
has_redis = backend.has_redis_backend()

# Direct backend access
mongo_backend = backend.get_mongo_backend()
redis_backend = backend.get_redis_backend()

# Model access
raw_model = backend.get_raw_model()
unified_model = backend.get_unified_model()
```

### Advanced Querying

#### MongoDB (through Unified Backend)
```python
# MongoDB-style queries
users = await backend.find_async({"age": {"$gte": 18}})
users = await backend.find_async({"skills": {"$in": ["Python", "JavaScript"]}})

# Aggregation pipelines (when using MongoDB)
if backend.get_current_backend_type() == BackendType.MONGO:
    pipeline = [
        {"$match": {"age": {"$gte": 18}}},
        {"$group": {"_id": "$department", "count": {"$sum": 1}}}
    ]
    results = await backend.get_mongo_backend().aggregate(pipeline)
```

#### Redis (through Unified Backend)
```python
# Switch to Redis for these queries
backend.switch_backend(BackendType.REDIS)

# Redis OM expressions
Model = backend.get_raw_model()
users = backend.find(Model.age >= 18)
users = backend.find(Model.name == "Alice")
users = backend.find(Model.skills << "Python")  # Contains
```

## Error Handling

The module provides comprehensive error handling:

```python
from mindtrace.database import DocumentNotFoundError, DuplicateInsertError

try:
    user = await backend.get_async("non_existent_id")
except DocumentNotFoundError as e:
    print(f"User not found: {e}")

try:
    await backend.insert_async(duplicate_user)
except DuplicateInsertError as e:
    print(f"User already exists: {e}")
```

## Testing

The database module includes comprehensive test coverage with both unit and integration tests.

### Test Structure

```
tests/
├── unit/mindtrace/database/          # Unit tests (no DB required)
│   ├── test_mongo_unit.py
│   ├── test_redis_unit.py
│   └── test_unified_unit.py
└── integration/mindtrace/database/   # Integration tests (DB required)
    ├── test_mongo.py
    ├── test_redis_odm.py
    └── test_unified.py
```

### Running Tests

#### Quick Start - All Tests
```bash
# Use the test script (handles everything automatically)
./scripts/run_tests.sh tests/unit/mindtrace/database tests/integration/mindtrace/database
```

#### Unit Tests Only (No Database Required)
```bash
# From project root
PYTHONPATH=mindtrace/core:mindtrace/database:$PYTHONPATH \
python -m pytest tests/unit/mindtrace/database/ -v
```

#### Integration Tests (Requires Databases)
```bash
# Start test databases
docker compose -f tests/docker-compose.yml up -d

# Run integration tests
PYTHONPATH=mindtrace/core:mindtrace/database:$PYTHONPATH \
python -m pytest tests/integration/mindtrace/database/ -v

# Stop test databases
docker compose -f tests/docker-compose.yml down
```

#### Targeted Testing
```bash
# Test only unified backend
./scripts/run_tests.sh --integration tests/integration/mindtrace/database/test_unified.py

# Test only MongoDB
./scripts/run_tests.sh --integration tests/integration/mindtrace/database/test_mongo.py

# Test only Redis
./scripts/run_tests.sh --integration tests/integration/mindtrace/database/test_redis_odm.py
```

### Test Coverage

The test suite covers:

- ✅ **CRUD Operations** - Create, Read, Update, Delete
- ✅ **Query Operations** - Find, filter, search
- ✅ **Error Handling** - All exception scenarios
- ✅ **Backend Switching** - Dynamic backend changes
- ✅ **Async/Sync Compatibility** - Both programming styles
- ✅ **Model Conversion** - Unified to backend-specific models
- ✅ **Edge Cases** - Duplicate keys, missing documents, invalid queries

## Examples

### Complete Example: User Management System

```python
import asyncio
from mindtrace.database import (
    UnifiedMindtraceODMBackend,
    UnifiedMindtraceDocument,
    BackendType,
    DocumentNotFoundError
)
from pydantic import Field
from typing import List

class User(UnifiedMindtraceDocument):
    name: str = Field(description="Full name")
    email: str = Field(description="Email address")  
    age: int = Field(ge=0, le=150, description="Age")
    department: str = Field(description="Department")
    skills: List[str] = Field(default_factory=list)
    
    class Meta:
        collection_name = "employees"
        global_key_prefix = "company"
        indexed_fields = ["email", "department", "skills"]
        unique_fields = ["email"]

async def main():
    # Setup backend with both MongoDB and Redis
    backend = UnifiedMindtraceODMBackend(
        unified_model_cls=User,
        mongo_db_uri="mongodb://localhost:27017",
        mongo_db_name="company",
        redis_url="redis://localhost:6379",
        preferred_backend=BackendType.MONGO
    )
    
    await backend.initialize_async()
    
    # Create some users
    users = [
        User(
            name="Alice Johnson",
            email="alice@company.com",
            age=30,
            department="Engineering",
            skills=["Python", "MongoDB", "Docker"]
        ),
        User(
            name="Bob Smith", 
            email="bob@company.com",
            age=25,
            department="Engineering",
            skills=["JavaScript", "Redis", "React"]
        ),
        User(
            name="Carol Davis",
            email="carol@company.com", 
            age=35,
            department="Marketing",
            skills=["Analytics", "SQL"]
        )
    ]
    
    # Insert users
    print("Creating users...")
    for user in users:
        try:
            inserted = await backend.insert_async(user)
            print(f"✅ Created: {inserted.name} (ID: {inserted.id})")
        except Exception as e:
            print(f"❌ Failed to create {user.name}: {e}")
    
    # Find engineers
    print("\n🔍 Finding engineers...")
    engineers = await backend.find_async({"department": "Engineering"})
    for eng in engineers:
        print(f"👨‍💻 {eng.name} - Skills: {', '.join(eng.skills)}")
    
    # Switch to Redis for fast lookups
    print("\n Switching to Redis for fast operations...")
    backend.switch_backend(BackendType.REDIS)
    
    # Insert more users in Redis
    redis_user = User(
        name="Dave Wilson",
        email="dave@company.com",
        age=28,
        department="DevOps",
        skills=["Kubernetes", "Redis", "Monitoring"]
    )
    
    redis_inserted = backend.insert(redis_user)
    print(f"Redis user created: {redis_inserted.name}")
    
    # Demonstrate backend isolation
    print(f"\n MongoDB users: {len(await backend.get_mongo_backend().all())}")
    print(f"Redis users: {len(backend.get_redis_backend().all())}")
    
    # Switch back to MongoDB
    backend.switch_backend(BackendType.MONGO)
    print(f"Back to MongoDB - Users: {len(await backend.all_async())}")

if __name__ == "__main__":
    asyncio.run(main())
```

### More Examples

Check out the `samples/database/` directory for additional examples:

- **`using_unified_backend.py`** - Comprehensive unified backend usage
- **Advanced querying patterns**
- **Backend switching strategies**
- **Error handling best practices**

## Best Practices

### 1. Model Design
```python
# ✅ Good: Clear, descriptive models
class Product(UnifiedMindtraceDocument):
    name: str = Field(description="Product name", min_length=1)
    price: float = Field(ge=0, description="Price in USD")
    category: str = Field(description="Product category")
    
    class Meta:
        collection_name = "products"
        indexed_fields = ["category", "name"]
        unique_fields = ["name"]

# ❌ Avoid: Unclear models without validation
class Product(UnifiedMindtraceDocument):
    n: str
    p: float
    c: str
```

### 2. Error Handling
```python
# ✅ Always handle database exceptions
try:
    user = await backend.get_async(user_id)
    print(f"Found user: {user.name}")
except DocumentNotFoundError:
    print("User not found - creating new user")
    user = await backend.insert_async(User(name="New User", email="new@example.com"))
except Exception as e:
    logger.error(f"Database error: {e}")
    # Handle appropriately
```

### 3. Backend Selection
```python
# ✅ Choose backends based on use case
if high_frequency_reads:
    backend.switch_backend(BackendType.REDIS)  # Fast reads
else:
    backend.switch_backend(BackendType.MONGO)  # Complex queries
```

### 4. Initialization
```python
# ✅ Initialize once at application startup
class DatabaseService:
    def __init__(self):
        self.backend = UnifiedMindtraceODMBackend(...)
    
    async def initialize(self):
        await self.backend.initialize_async()
        self.backend.initialize_sync()  # If you need both
    
    async def cleanup(self):
        # Cleanup if needed
        pass
```

## Contributing

When adding new features:

1. **Add tests** - Both unit and integration tests
2. **Update documentation** - Keep README and docstrings current
3. **Follow patterns** - Use existing code style and patterns
4. **Test thoroughly** - Run the full test suite

## Requirements

- **Python 3.9+**
- **MongoDB 4.4+** (for MongoDB backend)
- **Redis 6.0+** (for Redis backend)
- **Core dependencies**: `pydantic`, `beanie`, `redis-om-python`

## Need Help?

- Check the `samples/database/` directory for working examples
- Look at the test files for usage patterns
- Review the docstrings in the source code for detailed API documentation

The Mindtrace Database Module makes it easy to work with multiple databases through a single, powerful interface. Start simple with the unified backend, then customize as your needs grow!


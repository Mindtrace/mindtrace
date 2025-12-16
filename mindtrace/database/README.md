[![PyPI version](https://img.shields.io/pypi/v/mindtrace-database)](https://pypi.org/project/mindtrace-database/)
[![License](https://img.shields.io/pypi/l/mindtrace-database)](https://github.com/mindtrace/mindtrace/blob/main/mindtrace/database/LICENSE)
[![Downloads](https://static.pepy.tech/badge/mindtrace-database)](https://pepy.tech/projects/mindtrace-database)

# Mindtrace Database Module

A powerful, flexible Object-Document Mapping (ODM) system that provides a **unified interface** for working with multiple database backends in the Mindtrace project. Write once, run on MongoDB, Redis, or both!

## ⚠️ Breaking Changes

### Class Name Changes (Latest Version)

All backend class names have been simplified by removing the "Backend" suffix:

**Old Names (Deprecated):**
- `MindtraceODMBackend` → `MindtraceODM`
- `MongoMindtraceODMBackend` → `MongoMindtraceODM`
- `RedisMindtraceODMBackend` → `RedisMindtraceODM`
- `RegistryMindtraceODMBackend` → `RegistryMindtraceODM`
- `UnifiedMindtraceODMBackend` → `UnifiedMindtraceODM`

**Migration Guide:**

```python
# Old (deprecated)
from mindtrace.database import MongoMindtraceODMBackend, UnifiedMindtraceODMBackend

backend = MongoMindtraceODMBackend(model_cls=User, db_uri="...", db_name="...")
unified = UnifiedMindtraceODMBackend(unified_model_cls=User, ...)

# New (current)
from mindtrace.database import MongoMindtraceODM, UnifiedMindtraceODM

backend = MongoMindtraceODM(model_cls=User, db_uri="...", db_name="...")
unified = UnifiedMindtraceODM(unified_model_cls=User, ...)
```

**File Import Changes:**

Backend files have also been renamed (remove `_backend` suffix):
- `mindtrace_odm_backend.py` → `mindtrace_odm.py`
- `mongo_odm_backend.py` → `mongo_odm.py`
- `redis_odm_backend.py` → `redis_odm.py`
- `registry_odm_backend.py` → `registry_odm.py`
- `unified_odm_backend.py` → `unified_odm.py`

```python
# Old (deprecated)
from mindtrace.database.backends.mongo_odm_backend import MongoMindtraceODMBackend
from mindtrace.database.backends.unified_odm_backend import UnifiedMindtraceODMBackend

# New (current)
from mindtrace.database.backends.mongo_odm import MongoMindtraceODM
from mindtrace.database.backends.unified_odm import UnifiedMindtraceODM
```

**Note:** The recommended approach is to import from the main `mindtrace.database` module, which automatically provides the correct names:

```python
# Recommended - works with both old and new versions
from mindtrace.database import MongoMindtraceODM, UnifiedMindtraceODM, RedisMindtraceODM
```

## Key Features

- **Unified Backend System** - One interface for multiple databases
- **Dynamic Backend Switching** - Switch between MongoDB and Redis at runtime
- **Simplified Document Models** - Define once, use everywhere
- **Full Async/Sync Support** - Both MongoDB and Redis support both sync and async interfaces
- **Seamless Interface Compatibility** - Use sync code with async backends and vice versa
- **Advanced Querying** - Rich query capabilities across all backends
- **Comprehensive Error Handling** - Clear, actionable error messages
- **Full Test Coverage** - Thoroughly tested with unit and integration tests

## Quick Start

> **⚠️ Important**: Initialization is **deprecated and not required**! All operations automatically initialize the backend on first use. You can skip the `initialize()` step entirely - just create the backend and start using it!

### The Simple Way: Unified Documents

Define your document model once and use it with any backend:

```python
from mindtrace.database import UnifiedMindtraceDocument, UnifiedMindtraceODM, BackendType
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
backend = UnifiedMindtraceODM(
    unified_model_cls=User,
    mongo_db_uri="mongodb://localhost:27017",
    mongo_db_name="myapp",
    redis_url="redis://localhost:6379",
    preferred_backend=BackendType.MONGO  # Start with MongoDB
    # No initialization needed! Operations auto-initialize on first use.
    # If you need to control initialization, use auto_init and init_mode parameters:
    # auto_init=True,
    # init_mode=InitMode.ASYNC,  # Both backends use ASYNC (or SYNC)
    # If None, MongoDB defaults to ASYNC and Redis defaults to SYNC
)

# 3. Use it! (No initialization needed - operations auto-initialize on first use!)
# (Same API regardless of backend - both sync and async work!)
user = User(name="Alice", age=30, email="alice@example.com", skills=["Python"])

# Async operations (work with both MongoDB and Redis)
inserted_user = await backend.insert_async(user)
retrieved_user = await backend.get_async(inserted_user.id)
python_users = await backend.find_async({"skills": "Python"})
all_users = await backend.all_async()

# Sync operations (also work with both MongoDB and Redis!)
inserted_user = backend.insert(user)  # Works with MongoDB (via sync wrapper) or Redis (native)
retrieved_user = backend.get(inserted_user.id)
python_users = backend.find({"skills": "Python"})
all_users = backend.all()

# Switch backends on the fly!
backend.switch_backend(BackendType.REDIS)
redis_user = backend.insert(user)  # Now using Redis (sync)
# or
redis_user = await backend.insert_async(user)  # Redis with async interface
```

### Traditional Way: Backend-Specific Models

If you prefer more control, you can still define backend-specific models:

```python
from mindtrace.database import (
    MongoMindtraceODM, 
    RedisMindtraceODM,
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
mongo_backend = MongoMindtraceODM(
    model_cls=MongoUser,
    db_uri="mongodb://localhost:27017",
    db_name="myapp"
)

redis_backend = RedisMindtraceODM(
    model_cls=RedisUser,
    redis_url="redis://localhost:6379"
)
```

## Available Backends

### 1. UnifiedMindtraceODM (Recommended)

The flagship backend that provides a unified interface for multiple databases:

**Key Features:**
- **Single Interface**: One API for all backends
- **Runtime Switching**: Change backends without code changes
- **Automatic Model Generation**: Converts unified models to backend-specific formats
- **Flexible Configuration**: Use one or multiple backends

**Configuration Options:**
```python
# Option 1: Unified model (recommended)
backend = UnifiedMindtraceODM(
    unified_model_cls=MyUnifiedDoc,
    mongo_db_uri="mongodb://localhost:27017",
    mongo_db_name="mydb",
    redis_url="redis://localhost:6379",
    preferred_backend=BackendType.MONGO
)

# Option 2: Separate models
backend = UnifiedMindtraceODM(
    mongo_model_cls=MyMongoDoc,
    redis_model_cls=MyRedisDoc,
    mongo_db_uri="mongodb://localhost:27017",
    mongo_db_name="mydb",
    redis_url="redis://localhost:6379",
    preferred_backend=BackendType.REDIS
)

# Option 3: Single backend
backend = UnifiedMindtraceODM(
    unified_model_cls=MyUnifiedDoc,
    mongo_db_uri="mongodb://localhost:27017",
    mongo_db_name="mydb",
    preferred_backend=BackendType.MONGO
)
```

### 2. MongoMindtraceODM

Specialized MongoDB backend using Beanie ODM. **Natively async, but supports sync interface too!**

```python
from mindtrace.database import MongoMindtraceODM, MindtraceDocument

class User(MindtraceDocument):
    name: str
    email: str
    
    class Settings:
        name = "users"
        use_cache = False

backend = MongoMindtraceODM(
    model_cls=User,
    db_uri="mongodb://localhost:27017",
    db_name="myapp"
)

# The initialize() methods are deprecated and not necessary.

# If you need to control initialization timing, use constructor parameters:
# from mindtrace.database import InitMode
# backend = MongoMindtraceODM(
#     model_cls=User,
#     db_uri="mongodb://localhost:27017",
#     db_name="myapp",
#     auto_init=True,           # Auto-initialize in sync contexts
#     init_mode=InitMode.SYNC   # or InitMode.ASYNC (default for MongoDB)
# )

# Async operations (native)
user = await backend.insert(User(name="Alice", email="alice@example.com"))
all_users = await backend.all()

# Sync operations (wrapper methods - use from sync code!)
user = backend.insert_sync(User(name="Bob", email="bob@example.com"))
all_users = backend.all_sync()

# Supports MongoDB-specific features
pipeline = [{"$match": {"age": {"$gte": 18}}}]
results = await backend.aggregate(pipeline)
```

### 3. RedisMindtraceODM

High-performance Redis backend with JSON support. **Natively sync, but supports async interface too!**

```python
from mindtrace.database import RedisMindtraceODM, MindtraceRedisDocument
from redis_om import Field

class User(MindtraceRedisDocument):
    name: str = Field(index=True)
    email: str = Field(index=True)
    age: int = Field(index=True)
    
    class Meta:
        global_key_prefix = "myapp"

backend = RedisMindtraceODM(
    model_cls=User,
    redis_url="redis://localhost:6379"
)

# The initialize() methods are deprecated and not necessary.

# If you need to control initialization timing, use constructor parameters:
# from mindtrace.database import InitMode
# backend = RedisMindtraceODM(
#     model_cls=User,
#     redis_url="redis://localhost:6379",
#     auto_init=True,           # Auto-initialize immediately
#     init_mode=InitMode.SYNC   # or InitMode.ASYNC (default is SYNC for Redis)
# )

# Sync operations (native)
user = backend.insert(User(name="Alice", email="alice@example.com"))
all_users = backend.all()

# Async operations (wrapper methods - use from async code!)
user = await backend.insert_async(User(name="Bob", email="bob@example.com"))
all_users = await backend.all_async()

# Supports Redis-specific queries
users = backend.find(User.age >= 18)
```

### 4. LocalMindtraceODM

In-memory backend for testing and development:

```python
from mindtrace.database import LocalMindtraceODM
from pydantic import BaseModel

class User(BaseModel):
    name: str
    email: str

backend = LocalMindtraceODM(model_cls=User)
# No initialization needed - works immediately!
# (Same applies to all backends - initialization is optional and deprecated)
```

## API Reference

### Core Operations

All backends support both **sync and async** interfaces for all operations. Choose the style that fits your codebase!

#### Async Operations (Recommended for async code)

```python
# Insert a document
inserted_doc = await backend.insert_async(doc)

# Get document by ID
doc = await backend.get_async("doc_id")

# Delete document
await backend.delete_async("doc_id")

# Get all documents
all_docs = await backend.all_async()

# Find documents with filters
results = await backend.find_async({"name": "Alice"})
```

#### Sync Operations (Works with both MongoDB and Redis!)

```python
# Insert a document
inserted_doc = backend.insert(doc)

# Get document by ID
doc = backend.get("doc_id")

# Delete document
backend.delete("doc_id")

# Get all documents
all_docs = backend.all()

# Find documents with filters
results = backend.find({"name": "Alice"})
```

**Note**: 
- **MongoDB backend**: Sync methods use wrapper functions that run async code in an event loop
- **Redis backend**: Async methods use wrapper functions that call native sync methods
- **Unified backend**: Automatically routes to the appropriate method based on the active backend

### Understanding Sync/Async Wrappers

Both MongoDB and Redis backends now support both sync and async interfaces through wrapper methods:

#### MongoDB (Natively Async)
- **Native methods**: `insert()`, `get()`, `delete()`, `all()`, `find()`, `initialize()` - all async
- **Sync wrappers**: `insert_sync()`, `get_sync()`, `delete_sync()`, `all_sync()`, `find_sync()`, `initialize_sync()` - run async code in event loop
- **Use case**: Use sync wrappers when you need to call MongoDB from synchronous code

```python
# MongoDB backend - native async
mongo_backend = MongoMindtraceODM(...)
await mongo_backend.initialize()
user = await mongo_backend.insert(User(name="Alice"))

# MongoDB backend - sync wrapper (for sync code)
mongo_backend = MongoMindtraceODM(...)
mongo_backend.initialize_sync()  # Wrapper that runs async initialize()
user = mongo_backend.insert_sync(User(name="Bob"))  # Wrapper that runs async insert()
```

#### Redis (Natively Sync)
- **Native methods**: `insert()`, `get()`, `delete()`, `all()`, `find()`, `initialize()` - all sync
- **Async wrappers**: `insert_async()`, `get_async()`, `delete_async()`, `all_async()`, `find_async()`, `initialize_async()` - call sync methods directly
- **Use case**: Use async wrappers when you need to call Redis from asynchronous code

```python
# Redis backend - native sync
redis_backend = RedisMindtraceODM(...)
redis_backend.initialize()
user = redis_backend.insert(User(name="Alice"))

# Redis backend - async wrapper (for async code)
redis_backend = RedisMindtraceODM(...)
await redis_backend.initialize_async()  # Wrapper that calls sync initialize()
user = await redis_backend.insert_async(User(name="Bob"))  # Wrapper that calls sync insert()
```

#### Important Notes
- **Sync methods from async context**: MongoDB sync wrappers will raise `RuntimeError` if called from an async context (use native async methods instead)
- **Performance**: Wrappers add minimal overhead - MongoDB sync wrappers use `asyncio.run()`, Redis async wrappers are direct calls
- **Unified backend**: Automatically uses the correct method based on the active backend and your call style

### Sync/Async Compatibility

Both MongoDB and Redis backends now support both interfaces:

| Backend | Native Interface | Wrapper Interface |
|---------|-----------------|-------------------|
| MongoDB | Async (`insert`, `get`, etc.) | Sync (`insert_sync`, `get_sync`, etc.) |
| Redis | Sync (`insert`, `get`, etc.) | Async (`insert_async`, `get_async`, etc.) |

This means you can:
- Use sync code with MongoDB (via sync wrappers)
- Use async code with Redis (via async wrappers)
- Mix and match based on your needs!

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

- **CRUD Operations** - Create, Read, Update, Delete
- **Query Operations** - Find, filter, search
- **Error Handling** - All exception scenarios
- **Backend Switching** - Dynamic backend changes
- **Async/Sync Compatibility** - Both programming styles
- **Model Conversion** - Unified to backend-specific models
- **Edge Cases** - Duplicate keys, missing documents, invalid queries

## Examples

### Complete Example: User Management System

```python
import asyncio
from mindtrace.database import (
    UnifiedMindtraceODM,
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
    backend = UnifiedMindtraceODM(
        unified_model_cls=User,
        mongo_db_uri="mongodb://localhost:27017",
        mongo_db_name="company",
        redis_url="redis://localhost:6379",
        preferred_backend=BackendType.MONGO
    )
    
    # (The initialize() methods are deprecated and not necessary)
    
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
            print(f"Created: {inserted.name} (ID: {inserted.id})")
        except Exception as e:
            print(f"Failed to create {user.name}: {e}")
    
    # Find engineers
    print("\nFinding engineers...")
    engineers = await backend.find_async({"department": "Engineering"})
    for eng in engineers:
        print(f"{eng.name} - Skills: {', '.join(eng.skills)}")
    
    # Switch to Redis for fast lookups
    print("\nSwitching to Redis for fast operations...")
    backend.switch_backend(BackendType.REDIS)
    
    # Insert more users in Redis (both sync and async work!)
    redis_user = User(
        name="Dave Wilson",
        email="dave@company.com",
        age=28,
        department="DevOps",
        skills=["Kubernetes", "Redis", "Monitoring"]
    )
    
    # Use sync interface (native for Redis)
    redis_inserted = backend.insert(redis_user)
    print(f"Redis user created (sync): {redis_inserted.name}")
    
    # Or use async interface (wrapper for Redis)
    redis_user2 = User(
        name="Eve Brown",
        email="eve@company.com",
        age=32,
        department="DevOps",
        skills=["Docker", "CI/CD"]
    )
    redis_inserted2 = await backend.insert_async(redis_user2)
    print(f"Redis user created (async): {redis_inserted2.name}")
    
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
# Good: Clear, descriptive models
class Product(UnifiedMindtraceDocument):
    name: str = Field(description="Product name", min_length=1)
    price: float = Field(ge=0, description="Price in USD")
    category: str = Field(description="Product category")
    
    class Meta:
        collection_name = "products"
        indexed_fields = ["category", "name"]
        unique_fields = ["name"]

# Avoid: Unclear models without validation
class Product(UnifiedMindtraceDocument):
    n: str
    p: float
    c: str
```

### 2. Error Handling
```python
# Always handle database exceptions
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
# Choose backends based on use case
if high_frequency_reads:
    backend.switch_backend(BackendType.REDIS)  # Fast reads
else:
    backend.switch_backend(BackendType.MONGO)  # Complex queries
```

### 4. Initialization (Deprecated - Not Required)

**⚠️ Initialization is deprecated and not necessary!** All operations automatically initialize the backend on first use.

The `initialize()` and `initialize_sync()` methods are still available for backward compatibility and specific use cases, but you can safely skip them:

```python
# Recommended: Just use the backend - it auto-initializes!
backend = UnifiedMindtraceODM(
            unified_model_cls=User,
            mongo_db_uri="mongodb://localhost:27017",
            mongo_db_name="myapp",
            redis_url="redis://localhost:6379",
            preferred_backend=BackendType.MONGO
        )
    
# No initialization needed - operations auto-initialize!
user = await backend.insert_async(User(name="Alice", email="alice@example.com"))
```

**Recommended: Use constructor parameters for initialization control:**

```python
from mindtrace.database import InitMode

# Recommended: Control initialization via constructor parameters
backend = UnifiedMindtraceODM(
    unified_model_cls=User,
    mongo_db_uri="mongodb://localhost:27017",
    mongo_db_name="myapp",
    redis_url="redis://localhost:6379",
    preferred_backend=BackendType.MONGO,
    auto_init=True,                    # Auto-initialize in sync contexts
    init_mode=InitMode.ASYNC,          # Both backends use ASYNC (or SYNC)
    # If None, MongoDB defaults to ASYNC and Redis defaults to SYNC
)
# Backend is ready to use immediately (in sync contexts) or on first operation (in async contexts)
```

**Why initialization is deprecated:**
- **Lazy initialization**: Backends are created but NOT initialized until the first operation is called. Each operation (insert, get, delete, etc.) automatically checks if initialization is needed and initializes on-demand.
- **Simpler code**: No need to remember to call `initialize()` before using the backend - just use it!
- **Efficient**: Backends only connect to the database when actually needed (on first operation)
- **Constructor control**: Use `auto_init=True` and `init_mode` parameters if you want to initialize at creation time instead of on first operation

**When to use `auto_init=True` with `init_mode`:**
- **Performance**: Initialize once upfront rather than on first operation
- **Error handling**: Fail fast if database is unavailable at startup
- **Control**: Know exactly when database connections are established

**Note**: The `initialize()` and `initialize_sync()` methods are still available for backward compatibility, but using constructor parameters (`auto_init` and `init_mode`) is the recommended approach.

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


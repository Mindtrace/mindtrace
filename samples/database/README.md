# Database Module Samples

This directory contains focused examples for each ODM type in the Mindtrace Database Module.

## Samples Overview

### `redis_example.py`

Demonstrates **RedisMindtraceODM** operations:

- Multi-model support
- Synchronous operations (native for Redis)
- Asynchronous operations (wrapper)
- Redis OM query expressions
- CRUD operations

**Prerequisites:** Redis running on `localhost:6379`

**Best for:** Understanding Redis-specific features and sync/async compatibility

### `mongo_example.py`

Demonstrates **MongoMindtraceODM** operations:

- Multi-model support
- Asynchronous operations (native for MongoDB)
- Synchronous operations (wrapper)
- Linked documents with `fetch_links`
- Beanie query expressions
- MongoDB-style queries
- CRUD operations

**Prerequisites:** MongoDB running on `localhost:27017`

**Best for:** Understanding MongoDB-specific features and document linking

### `unified_example.py`

Demonstrates **UnifiedMindtraceODM** operations:

- Multi-model support
- MongoDB backend operations
- Redis backend operations
- Unified interface across backends
- CRUD operations

**Prerequisites:** 
- MongoDB running on `localhost:27017`
- Redis running on `localhost:6379`

**Best for:** Understanding the unified interface and working with multiple backends

### `registry_example.py`

Demonstrates **RegistryMindtraceODM** operations:

- Single model mode
- Multi-model mode
- Custom archiver implementation
- Error handling
- CRUD operations

**Prerequisites:** `mindtrace-registry` module installed

**Best for:** Understanding the Registry-based storage system

## Prerequisites

Before running the examples, ensure you have:

1. **MongoDB** running (for `mongo_example.py` and `unified_example.py`)
   ```bash
   docker run -d -p 27017:27017 --name mongo mongo:latest
   ```

2. **Redis** running (for `redis_example.py` and `unified_example.py`)
   ```bash
   docker run -d -p 6379:6379 --name redis redis:latest
   ```

3. **Python dependencies** installed:
   ```bash
   pip install mindtrace-database
   # For registry example:
   pip install mindtrace-registry
   ```

## Running the Examples

### Redis Example
```bash
python samples/database/redis_example.py
```

### MongoDB Example
```bash
python samples/database/mongo_example.py
```

### Unified ODM Example
```bash
python samples/database/unified_example.py
```

### Registry ODM Example
```bash
python samples/database/registry_example.py
```

## Key Concepts Demonstrated

### 1. Model Definitions
Each example shows how to define models for the specific ODM:
- **Redis**: Uses `MindtraceRedisDocument` with `Field(index=True)`
- **MongoDB**: Uses `MindtraceDocument` with `Link` for relationships
- **Unified**: Uses `UnifiedMindtraceDocument` - works with both backends
- **Registry**: Uses plain `BaseModel` with custom archivers

### 2. Multi-Model Support
All ODMs support managing multiple document types:
```python
db = ODM(models={"user": User, "address": Address})
await db.user.insert_async(...)
await db.address.insert_async(...)
```

### 3. Sync/Async Compatibility
- **Redis**: Native sync, async wrapper available
- **MongoDB**: Native async, sync wrapper available
- **Unified**: Supports both based on active backend

### 4. Query Patterns
- **Redis**: Redis OM expressions (`UserRedis.age >= 30`)
- **MongoDB**: Beanie expressions (`User.age >= 30`) or dict queries (`{"age": {"$gte": 30}}`)
- **Unified**: Uses backend-specific query patterns

## Next Steps

After running the examples:

1. **Read the Documentation** - See `mindtrace/database/README.md` for full API reference
2. **Explore the Tests** - Check `tests/` directory for more usage patterns
3. **Build Your App** - Use these patterns in your own projects

## Need Help?

- Check the main README: `mindtrace/database/README.md`
- Review the test files: `tests/integration/mindtrace/database/`
- Look at the source code docstrings for detailed API documentation

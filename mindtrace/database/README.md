[![PyPI version](https://img.shields.io/pypi/v/mindtrace-database)](https://pypi.org/project/mindtrace-database/)
[![License](https://img.shields.io/pypi/l/mindtrace-database)](https://github.com/mindtrace/mindtrace/blob/main/mindtrace/database/LICENSE)
[![Downloads](https://static.pepy.tech/badge/mindtrace-database)](https://pepy.tech/projects/mindtrace-database)

# Mindtrace Database Module

A powerful, flexible Object-Document Mapping (ODM) system that provides a **unified interface** for working with multiple database backends in the Mindtrace project. Write once, run on MongoDB, Redis, or both.

## Key Features

- **Unified Interface** - One API for multiple databases
- **Multi-Model Support** - Manage multiple document types in a single ODM instance
- **Dynamic Switching** - Switch between MongoDB and Redis at runtime
- **Simplified Document Models** - Define once, use everywhere
- **Full Async/Sync Support** - Both MongoDB and Redis support sync and async interfaces
- **Seamless Interface Compatibility** - Use sync code with async databases and vice versa
- **Advanced Querying** - Rich query capabilities across all databases
- **Comprehensive Error Handling** - Clear, actionable error messages
- **Full Test Coverage** - Thoroughly tested with unit and integration tests

## Quick Start

### The Simple Way: Unified Documents

Define your document model once and use it with any database:

```python
from mindtrace.database import UnifiedMindtraceDocument, UnifiedMindtraceODM, BackendType

from pydantic import Field

# 1. Define your document model (works with both MongoDB and Redis)
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

# 2. Create ODM instance (supports both MongoDB and Redis)
db = UnifiedMindtraceODM(
    unified_model_cls=User,
    mongo_db_uri="mongodb://localhost:27017",
    mongo_db_name="myapp",
    redis_url="redis://localhost:6379",
    preferred_backend=BackendType.MONGO  # Start with MongoDB
    # init_mode=InitMode.ASYNC,  # Both use ASYNC (or SYNC)
    # If None, MongoDB defaults to ASYNC and Redis defaults to SYNC
)

# 3. Use it (Same API regardless of database - both sync and async work)
user = User(name="Alice", age=30, email="alice@example.com", skills=["Python"])

# Async operations (work with both MongoDB and Redis)
inserted_user = await db.insert_async(user)
retrieved_user = await db.get_async(inserted_user.id)
retrieved_user.age = 31
updated_user = await db.update_async(retrieved_user)
python_users = await db.find_async({"skills": "Python"})
all_users = await db.all_async()

# Sync operations (also work with both MongoDB and Redis)
inserted_user = db.insert(user)
retrieved_user = db.get(inserted_user.id)
retrieved_user.age = 31
updated_user = db.update(retrieved_user)
python_users = db.find({"skills": "Python"})
all_users = db.all()

# Switch databases on the fly
db.switch_backend(BackendType.REDIS)
redis_user = db.insert(user)  # Now using Redis (sync)
# or
redis_user = await db.insert_async(user)  # Redis with async interface

# Multi-model mode (works with all ODMs)
db = UnifiedMindtraceODM(
    unified_models={'user': User, 'address': Address},
    mongo_db_uri="mongodb://localhost:27017",
    mongo_db_name="myapp",
    redis_url="redis://localhost:6379"
)

# Access models via attributes
address = await db.address.insert_async(Address(street="123 Main St", city="NYC"))
user = await db.user.insert_async(User(name="Alice", email="alice@example.com"))

# All operations work per model
users = await db.user.all_async()
addresses = await db.address.all_async()
```

### Traditional Way: Database-Specific Models

If you prefer more control, you can define database-specific models:

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
mongo_db = MongoMindtraceODM(
    model_cls=MongoUser,
    db_uri="mongodb://localhost:27017",
    db_name="myapp"
)

redis_db = RedisMindtraceODM(
    model_cls=RedisUser,
    redis_url="redis://localhost:6379"
)
```

## Multi-Model Support

All ODMs now support managing multiple document types in a single instance. This allows you to work with related models (e.g., `User` and `Address`) through a single ODM instance with attribute-based access.

### Usage Pattern

```python
# Instead of creating separate ODMs for each model:
user_db = MongoMindtraceODM(model_cls=User, ...)
address_db = MongoMindtraceODM(model_cls=Address, ...)

# Use multi-model mode:
db = MongoMindtraceODM(
    models={'user': User, 'address': Address},
    db_uri="mongodb://localhost:27017",
    db_name="myapp"
)

# Access models via attributes
await db.user.insert(user)
await db.address.insert(address)
users = await db.user.all()
addresses = await db.address.all()
```

**Benefits:**
- **Shared Connection** - All models share the same database connection
- **Unified Initialization** - All models initialize together
- **Cleaner Code** - Single ODM instance instead of multiple
- **Consistent API** - Same operations work across all models

**Note:** In multi-model mode, you must use attribute-based access (`db.user.insert()`). Direct methods (`db.insert()`) will raise a `ValueError` to prevent ambiguity.

## Available ODMs

### 1. UnifiedMindtraceODM (Recommended)

The flagship ODM that provides a unified interface for multiple databases:

**Key Features:**
- **Single Interface**: One API for all databases
- **Runtime Switching**: Change databases without code changes
- **Automatic Model Generation**: Converts unified models to database-specific formats
- **Flexible Configuration**: Use one or multiple databases

**Configuration Options:**
```python
# Option 1: Single unified model
db = UnifiedMindtraceODM(
    unified_model_cls=MyUnifiedDoc,
    mongo_db_uri="mongodb://localhost:27017",
    mongo_db_name="mydb",
    redis_url="redis://localhost:6379",
    preferred_backend=BackendType.MONGO
)

# Option 2: Multiple unified models (multi-model mode)
db = UnifiedMindtraceODM(
    unified_models={'user': User, 'address': Address},
    mongo_db_uri="mongodb://localhost:27017",
    mongo_db_name="mydb",
    redis_url="redis://localhost:6379",
    preferred_backend=BackendType.MONGO
)
# Access via: db.user, db.address

# Option 3: Separate models
db = UnifiedMindtraceODM(
    mongo_model_cls=MyMongoDoc,
    redis_model_cls=MyRedisDoc,
    mongo_db_uri="mongodb://localhost:27017",
    mongo_db_name="mydb",
    redis_url="redis://localhost:6379",
    preferred_backend=BackendType.REDIS
)

# Option 4: Single database
db = UnifiedMindtraceODM(
    unified_model_cls=MyUnifiedDoc,
    mongo_db_uri="mongodb://localhost:27017",
    mongo_db_name="mydb",
    preferred_backend=BackendType.MONGO
)
```

### 2. MongoMindtraceODM

Specialized MongoDB ODM using Beanie. **Natively async, but supports sync interface too**

#### Single Model Mode

```python
from mindtrace.database import MongoMindtraceODM, MindtraceDocument

class User(MindtraceDocument):
    name: str
    email: str
    
    class Settings:
        name = "users"
        use_cache = False

db = MongoMindtraceODM(
    model_cls=User,
    db_uri="mongodb://localhost:27017",
    db_name="myapp"
)

# Async operations (native)
user = await db.insert(User(name="Alice", email="alice@example.com"))
user.age = 31
updated_user = await db.update(user)
all_users = await db.all()

# Sync operations (wrapper methods - use from sync code)
user = db.insert_sync(User(name="Bob", email="bob@example.com"))
user.age = 32
updated_user = db.update_sync(user)
all_users = db.all_sync()

# Supports MongoDB-specific features
pipeline = [{"$match": {"age": {"$gte": 18}}}]
results = await db.aggregate(pipeline)
```

#### Multi-Model Mode

```python
from mindtrace.database import MongoMindtraceODM, MindtraceDocument

class Address(MindtraceDocument):
    street: str
    city: str
    
    class Settings:
        name = "addresses"
        use_cache = False

class User(MindtraceDocument):
    name: str
    email: str
    
    class Settings:
        name = "users"
        use_cache = False

# Create ODM with multiple models
db = MongoMindtraceODM(
    models={'user': User, 'address': Address},
    db_uri="mongodb://localhost:27017",
    db_name="myapp"
)

# Access models via attribute-based access
address = await db.address.insert(Address(street="123 Main St", city="NYC"))
user = await db.user.insert(User(name="Alice", email="alice@example.com"))

# All operations work per model
users = await db.user.all()
addresses = await db.address.all()
```

#### Working with Linked Documents (fetch_links)

MongoDB supports linking documents using Beanie's `Link` type. Use `fetch_links=True` to automatically fetch linked documents:

```python
from mindtrace.database import Link, MongoMindtraceODM, MindtraceDocument
from typing import Optional

class Address(MindtraceDocument):
    street: str
    city: str
    
    class Settings:
        name = "addresses"
        use_cache = False

class User(MindtraceDocument):
    name: str
    email: str
    address: Optional[Link[Address]] = None
    
    class Settings:
        name = "users"
        use_cache = False

db = MongoMindtraceODM(
    models={'user': User, 'address': Address},
    db_uri="mongodb://localhost:27017",
    db_name="myapp"
)

# Create linked documents
address = await db.address.insert(Address(street="123 Main St", city="NYC"))
user = await db.user.insert(User(name="Alice", email="alice@example.com", address=address))

# Fetch with linked documents using fetch_links=True
user_with_address = await db.user.get(user.id, fetch_links=True)
print(f"User: {user_with_address.name}, Address: {user_with_address.address.street}")

# Find with linked documents
users = await db.user.find(User.name == "Alice", fetch_links=True)
for u in users:
    if u.address:
        print(f"{u.name} lives at {u.address.street}")

# Without fetch_links, address will be a Link object (not fetched)
user_without_links = await db.user.get(user.id)
# user_without_links.address is a Link object, not the actual Address document
```

### 3. RedisMindtraceODM

High-performance Redis ODM with JSON support. **Natively sync, but supports async interface too**

#### Single Model Mode

```python
from mindtrace.database import RedisMindtraceODM, MindtraceRedisDocument
from redis_om import Field

class User(MindtraceRedisDocument):
    name: str = Field(index=True)
    email: str = Field(index=True)
    age: int = Field(index=True)
    
    class Meta:
        global_key_prefix = "myapp"

db = RedisMindtraceODM(
    model_cls=User,
    redis_url="redis://localhost:6379"
)

# Sync operations (native)
user = db.insert(User(name="Alice", email="alice@example.com"))
user.age = 31
updated_user = db.update(user)
all_users = db.all()

# Async operations (wrapper methods - use from async code)
user = await db.insert_async(User(name="Bob", email="bob@example.com"))
user.age = 32
updated_user = await db.update_async(user)
all_users = await db.all_async()

# Supports Redis-specific queries
users = db.find(User.age >= 18)
```

#### Multi-Model Mode

```python
from mindtrace.database import RedisMindtraceODM, MindtraceRedisDocument
from redis_om import Field

class Address(MindtraceRedisDocument):
    street: str = Field(index=True)
    city: str = Field(index=True)
    
    class Meta:
        global_key_prefix = "myapp"

class User(MindtraceRedisDocument):
    name: str = Field(index=True)
    email: str = Field(index=True)
    address_id: Optional[str] = None
    
    class Meta:
        global_key_prefix = "myapp"

# Create ODM with multiple models
db = RedisMindtraceODM(
    models={'user': User, 'address': Address},
    redis_url="redis://localhost:6379"
)

# Access models via attribute-based access
address = db.address.insert(Address(street="123 Main St", city="NYC"))
user = db.user.insert(User(name="Alice", email="alice@example.com", address_id=address.id))

# All operations work per model
users = db.user.all()
addresses = await db.address.all_async()
```

### 4. RegistryMindtraceODM

Flexible ODM using the Mindtrace Registry system, supporting local storage, GCP, and other storage options:

#### Single Model Mode

```python
from mindtrace.database import RegistryMindtraceODM, DocumentNotFoundError
from mindtrace.registry import Registry, Archiver
from typing import Any, Type
from pydantic import BaseModel
from pathlib import Path

class User(BaseModel):
    name: str
    email: str

class UserArchiver(Archiver):
    def save(self, user: User):
        with open(Path(self.uri) / "user.json", "w") as f:
            f.write(user.model_dump_json())

    def load(self, data_type: Type[Any]) -> User:
        with open(Path(self.uri) / "user.json", "r") as f:
            return User.model_validate_json(f.read())

Registry.register_default_materializer(User, UserArchiver)

db = RegistryMindtraceODM(model_cls=User)

user = User(name="John Doe", email="john.doe@example.com")
inserted_user = db.insert(user)

# Update the user
inserted_user.name = "John Smith"
updated_user = db.update(inserted_user)

# Retrieve by ID (raises DocumentNotFoundError if not found)
try:
    user = db.get(inserted_user.id)
except DocumentNotFoundError:
    print("User not found")
```

#### Multi-Model Mode

```python
from mindtrace.database import RegistryMindtraceODM
from mindtrace.registry import Registry, Archiver
from typing import Any, Type
from pydantic import BaseModel

class User(BaseModel):
    name: str
    email: str

class Address(BaseModel):
    street: str
    city: str

# Register materializers for both models
Registry.register_default_materializer(User, UserArchiver)
Registry.register_default_materializer(Address, AddressArchiver)

# Create ODM with multiple models
db = RegistryMindtraceODM(
    models={'user': User, 'address': Address}
)

# Access models via attribute-based access
address = db.address.insert(Address(street="123 Main St", city="NYC"))
user = db.user.insert(User(name="John Doe", email="john@example.com"))

# All operations work per model
users = db.user.all()
addresses = db.address.all()
```

**With GCP Storage:**

```python
from mindtrace.database import RegistryMindtraceODM
from mindtrace.registry import Registry, GCPRegistryBackend, Archiver
from typing import Any, Type
from pydantic import BaseModel
from pathlib import Path

class User(BaseModel):
    name: str
    email: str

class UserArchiver(Archiver):
    def save(self, user: User):
        with open(Path(self.uri) / "user.json", "w") as f:
            f.write(user.model_dump_json())

    def load(self, data_type: Type[Any]) -> User:
        with open(Path(self.uri) / "user.json", "r") as f:
            return User.model_validate_json(f.read())

Registry.register_default_materializer(User, UserArchiver)

gcp_registry_backend = GCPRegistryBackend(
    uri="gs://my-bucket",
    project_id="my-project",
    bucket_name="my-bucket",
)

db = RegistryMindtraceODM(model_cls=User, backend=gcp_registry_backend)

user = User(name="John Doe", email="john.doe@example.com")
inserted_user = db.insert(user)

# Update the user
inserted_user.name = "John Smith"
updated_user = db.update(inserted_user)

# Retrieve by ID
user = db.get(inserted_user.id)
```

## API Reference

### Core Operations

All ODMs support both **sync and async** interfaces for all operations. Choose the style that fits your codebase.

#### Async Operations (Recommended for async code)

```python
# Insert a document
inserted_doc = await db.insert_async(doc)

# Get document by ID
doc = await db.get_async("doc_id")

# Get document with linked documents (MongoDB only)
doc_with_links = await db.get_async("doc_id", fetch_links=True)

# Update document
doc.name = "Updated Name"
updated_doc = await db.update_async(doc)

# Delete document
await db.delete_async("doc_id")

# Get all documents
all_docs = await db.all_async()

# Find documents with filters
results = await db.find_async({"name": "Alice"})

# Find documents with linked documents (MongoDB only)
results_with_links = await db.find_async({"name": "Alice"}, fetch_links=True)
```

#### Sync Operations (Works with both MongoDB and Redis)

```python
# Insert a document
inserted_doc = db.insert(doc)

# Get document by ID
doc = db.get("doc_id")

# Update document
doc.name = "Updated Name"
updated_doc = db.update(doc)

# Delete document
db.delete("doc_id")

# Get all documents
all_docs = db.all()

# Find documents with filters
results = db.find({"name": "Alice"})
```

**Note**: 
- **MongoDB**: Sync methods use wrapper functions that run async code in an event loop
- **Redis**: Async methods run sync operations in a thread pool to avoid blocking the event loop
- **Unified ODM**: Automatically routes to the appropriate method based on the active database
- **Document IDs**: All backends provide a consistent `id` attribute on returned documents (MongoDB uses `id`, Redis uses `pk` internally but exposes it as `id`)

### Sync/Async Compatibility

Both MongoDB and Redis ODMs support both interfaces:

| Database | Native Interface | Wrapper Interface |
|----------|-----------------|-------------------|
| MongoDB | Async (`insert`, `get`, etc.) | Sync (`insert_sync`, `get_sync`, etc.) |
| Redis | Sync (`insert`, `get`, etc.) | Async (`insert_async`, `get_async`, etc.) |

This means you can:
- Use sync code with MongoDB (via sync wrappers)
- Use async code with Redis (via async wrappers)
- Mix and match based on your needs

### UnifiedMindtraceODM Specific

Additional methods for the unified ODM:

```python
# Database management
db.switch_backend(BackendType.REDIS)
current_type = db.get_current_backend_type()
is_async = db.is_async()

# Database availability
has_mongo = db.has_mongo_backend()
has_redis = db.has_redis_backend()

# Direct access to underlying ODMs
mongo_odm = db.get_mongo_backend()
redis_odm = db.get_redis_backend()

# Model access
raw_model = db.get_raw_model()
unified_model = db.get_unified_model()
```

### Advanced Querying

#### MongoDB (through UnifiedMindtraceODM)
```python
from mindtrace.database import Link

# MongoDB-style queries
users = await db.find_async({"age": {"$gte": 18}})
users = await db.find_async({"skills": {"$in": ["Python", "JavaScript"]}})

# Fetch linked documents using fetch_links=True
user = await db.get_async(user_id, fetch_links=True)
if user.address:
    print(f"User lives at {user.address.street}")

# Find with linked documents
users = await db.find_async({"name": "Alice"}, fetch_links=True)
for u in users:
    if u.address:
        print(f"{u.name} - {u.address.city}")

# Using Beanie expressions with links (get raw model first)
UserMongo = db.get_raw_model()
users = await db.find_async(UserMongo.name == "Alice", fetch_links=True)

# Aggregation pipelines (when using MongoDB)
if db.get_current_backend_type() == BackendType.MONGO:
    pipeline = [
        {"$match": {"age": {"$gte": 18}}},
        {"$group": {"_id": "$department", "count": {"$sum": 1}}}
    ]
    results = await db.get_mongo_backend().aggregate(pipeline)
```

#### Redis (through UnifiedMindtraceODM)
```python
# Switch to Redis for these queries
db.switch_backend(BackendType.REDIS)

# Redis OM expressions
Model = db.get_raw_model()
users = db.find(Model.age >= 18)
users = db.find(Model.name == "Alice")
users = db.find(Model.skills << "Python")  # Contains
```

## Initialization Options

By default, ODMs auto-initialize on first operation. For more control, use constructor parameters:

```python
from mindtrace.database import InitMode

db = UnifiedMindtraceODM(
    unified_model_cls=User,
    mongo_db_uri="mongodb://localhost:27017",
    mongo_db_name="myapp",
    redis_url="redis://localhost:6379",
    preferred_backend=BackendType.MONGO,
    auto_init=True,              # Initialize at creation time
    init_mode=InitMode.SYNC,     # Use sync initialization
)
```

**InitMode options:**
- `InitMode.SYNC` - Synchronous initialization (blocks until complete)
- `InitMode.ASYNC` - Deferred initialization (completes on first async operation)

**Default behavior:**
- MongoDB defaults to `InitMode.ASYNC`
- Redis defaults to `InitMode.SYNC`

## Error Handling

The module provides comprehensive error handling with consistent exceptions across all backends:

```python
from mindtrace.database import DocumentNotFoundError, DuplicateInsertError

try:
    user = await db.get_async("non_existent_id")
except DocumentNotFoundError as e:
    print(f"User not found: {e}")

try:
    await db.insert_async(duplicate_user)
except DuplicateInsertError as e:
    print(f"User already exists: {e}")

# All backends raise DocumentNotFoundError (not KeyError) for consistency
try:
    user = db.get("missing_id")
except DocumentNotFoundError:
    print("Document not found")

# Multi-model mode errors
try:
    db.insert(user)  # In multi-model mode, this raises ValueError
except ValueError as e:
    print(f"Use db.model_name.insert() instead: {e}")
```


```python
from mindtrace.database import DocumentNotFoundError, DuplicateInsertError

try:
    user = await db.get_async("non_existent_id")
except DocumentNotFoundError as e:
    print(f"User not found: {e}")

try:
    await db.insert_async(duplicate_user)
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
│   ├── test_registry_odm_backend.py
│   └── test_unified_unit.py
└── integration/mindtrace/database/   # Integration tests (DB required)
    ├── test_mongo.py
    ├── test_redis_odm.py
    ├── test_registry_odm.py
    └── test_unified.py
```

### Running Tests

#### Quick Start - All Tests
```bash
ds test: database
```

#### Unit Tests Only
```bash
ds test: database --unit
```

#### Integration Tests (Containers managed by test script)
```bash
ds test: database --integration
```

#### Targeted Testing
```bash
# Test only unified backend
ds test: tests/integration/mindtrace/database/test_unified.py

# Test only MongoDB
ds test: tests/integration/mindtrace/database/test_mongo.py

# Test only Redis
ds test: tests/integration/mindtrace/database/test_redis_odm.py
```

### Test Coverage

The test suite covers:

- **CRUD Operations** - Create, Read, Update, Delete
- **Query Operations** - Find, filter, search
- **Error Handling** - All exception scenarios
- **Database Switching** - Dynamic database changes
- **Async/Sync Compatibility** - Both programming styles
- **Model Conversion** - Unified to database-specific models
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
    # Setup with both MongoDB and Redis
    db = UnifiedMindtraceODM(
        unified_model_cls=User,
        mongo_db_uri="mongodb://localhost:27017",
        mongo_db_name="company",
        redis_url="redis://localhost:6379",
        preferred_backend=BackendType.MONGO
    )
    
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
            inserted = await db.insert_async(user)
            print(f"Created: {inserted.name} (ID: {inserted.id})")
        except Exception as e:
            print(f"Failed to create {user.name}: {e}")
    
    # Find engineers
    print("\nFinding engineers...")
    engineers = await db.find_async({"department": "Engineering"})
    for eng in engineers:
        print(f"{eng.name} - Skills: {', '.join(eng.skills)}")
    
    # Switch to Redis for fast lookups
    print("\nSwitching to Redis for fast operations...")
    db.switch_backend(BackendType.REDIS)
    
    # Insert more users in Redis (both sync and async work)
    redis_user = User(
        name="Dave Wilson",
        email="dave@company.com",
        age=28,
        department="DevOps",
        skills=["Kubernetes", "Redis", "Monitoring"]
    )
    
    # Use sync interface (native for Redis)
    redis_inserted = db.insert(redis_user)
    print(f"Redis user created (sync): {redis_inserted.name}")
    
    # Or use async interface (wrapper for Redis)
    redis_user2 = User(
        name="Eve Brown",
        email="eve@company.com",
        age=32,
        department="DevOps",
        skills=["Docker", "CI/CD"]
    )
    redis_inserted2 = await db.insert_async(redis_user2)
    print(f"Redis user created (async): {redis_inserted2.name}")
    
    # Demonstrate data isolation
    print(f"\nMongoDB users: {len(await db.get_mongo_backend().all())}")
    print(f"Redis users: {len(db.get_redis_backend().all())}")
    
    # Switch back to MongoDB
    db.switch_backend(BackendType.MONGO)
    print(f"Back to MongoDB - Users: {len(await db.all_async())}")

if __name__ == "__main__":
    asyncio.run(main())
```

### More Examples

Check out the `samples/database/` directory for additional examples:

- **`using_unified_backend.py`** - Comprehensive unified ODM usage
- **Advanced querying patterns**
- **Database switching strategies**
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
    user = await db.get_async(user_id)
    print(f"Found user: {user.name}")
except DocumentNotFoundError:
    print("User not found - creating new user")
    user = await db.insert_async(User(name="New User", email="new@example.com"))
except Exception as e:
    logger.error(f"Database error: {e}")
    # Handle appropriately
```

### 3. Database Selection
```python
# Choose database based on use case
if high_frequency_reads:
    db.switch_backend(BackendType.REDIS)  # Fast reads
else:
    db.switch_backend(BackendType.MONGO)  # Complex queries
```

## Contributing

When adding new features:

1. **Add tests** - Both unit and integration tests
2. **Update documentation** - Keep README and docstrings current
3. **Follow patterns** - Use existing code style and patterns
4. **Test thoroughly** - Run the full test suite

## Requirements

- **MongoDB 4.4+** (for MongoMindtraceODM)
- **Redis 6.0+** (for RedisMindtraceODM)
- **Core dependencies**: `pydantic`, `beanie`, `redis-om-python`

## Need Help?

- Check the `samples/database/` directory for working examples
- Look at the test files for usage patterns
- Review the docstrings in the source code for detailed API documentation

The Mindtrace Database Module makes it easy to work with multiple databases through a single, powerful interface.

---

## Breaking Changes

### Class Name Changes (v0.6.0)

All ODM class names have been simplified by removing the "Backend" suffix:

| Old Name | New Name |
|----------|----------|
| `MindtraceODMBackend` | `MindtraceODM` |
| `MongoMindtraceODMBackend` | `MongoMindtraceODM` |
| `RedisMindtraceODMBackend` | `RedisMindtraceODM` |
| `RegistryMindtraceODMBackend` | `RegistryMindtraceODM` |
| `UnifiedMindtraceODMBackend` | `UnifiedMindtraceODM` |

**File names also updated:**

| Old File | New File |
|----------|----------|
| `mindtrace_odm_backend.py` | `mindtrace_odm.py` |
| `mongo_odm_backend.py` | `mongo_odm.py` |
| `redis_odm_backend.py` | `redis_odm.py` |
| `registry_odm_backend.py` | `registry_odm.py` |
| `unified_odm_backend.py` | `unified_odm.py` |

**Migration:**

```python
# Old
from mindtrace.database import MongoMindtraceODMBackend, UnifiedMindtraceODMBackend
db = MongoMindtraceODMBackend(model_cls=User, db_uri="...", db_name="...")

# New
from mindtrace.database import MongoMindtraceODM, UnifiedMindtraceODM
db = MongoMindtraceODM(model_cls=User, db_uri="...", db_name="...")
```

[![PyPI version](https://img.shields.io/pypi/v/mindtrace-database)](https://pypi.org/project/mindtrace-database/)
[![License](https://img.shields.io/pypi/l/mindtrace-database)](https://github.com/mindtrace/mindtrace/blob/main/mindtrace/database/LICENSE)
[![Downloads](https://static.pepy.tech/badge/mindtrace-database)](https://pepy.tech/projects/mindtrace-database)

# Mindtrace Database

The `Database` module provides Mindtrace’s object-document mapping layer for MongoDB, Redis, Registry-backed storage, and unified multi-backend workflows.

## Features

- **Unified ODM interface** through `UnifiedMindtraceODM`
- **Backend-specific ODMs** for MongoDB, Redis, and Registry-backed storage
- **Single-model and multi-model operation** in the same API style
- **Sync and async access patterns** across all supported backends
- **Unified document models** that can target both MongoDB and Redis
- **Consistent exceptions** such as `DocumentNotFoundError` and `DuplicateInsertError`

## Quick Start

```python
import asyncio

from pydantic import Field

from mindtrace.database import BackendType, UnifiedMindtraceDocument, UnifiedMindtraceODM


class User(UnifiedMindtraceDocument):
    name: str = Field(description="User name")
    email: str = Field(description="Email address")
    age: int = Field(ge=0)

    class Meta:
        collection_name = "users"
        global_key_prefix = "myapp"
        indexed_fields = ["email", "name"]
        unique_fields = ["email"]


async def main():
    db = UnifiedMindtraceODM(
        unified_model_cls=User,
        mongo_db_uri="mongodb://localhost:27017",
        mongo_db_name="myapp",
        redis_url="redis://localhost:6379",
        preferred_backend=BackendType.MONGO,
    )

    user = User(name="Alice", email="alice@example.com", age=30)
    inserted = await db.insert_async(user)
    fetched = await db.get_async(inserted.id)
    print(fetched)


asyncio.run(main())
```

In practice, the database module gives you a common way to define document models and CRUD workflows while choosing the backend that best fits your application.

## Core Concepts

The package revolves around four main ODM styles:

- **`UnifiedMindtraceODM`** — one API over MongoDB and/or Redis
- **`MongoMindtraceODM`** — MongoDB-specific ODM built on Beanie
- **`RedisMindtraceODM`** — Redis-specific ODM built on redis-om
- **`RegistryMindtraceODM`** — Registry-backed ODM for simpler local or storage-backed document persistence

The package also provides matching document model bases:

- `UnifiedMindtraceDocument`
- `MindtraceDocument`
- `MindtraceRedisDocument`

## UnifiedMindtraceODM

`UnifiedMindtraceODM` is the recommended starting point when you want one API that can work across MongoDB and Redis.

### Unified document model

```python
from pydantic import Field

from mindtrace.database import UnifiedMindtraceDocument


class User(UnifiedMindtraceDocument):
    name: str = Field(description="User name")
    email: str = Field(description="Email")
    age: int = Field(ge=0)

    class Meta:
        collection_name = "users"
        global_key_prefix = "myapp"
        indexed_fields = ["email", "name"]
        unique_fields = ["email"]
```

### Unified ODM setup

```python
from mindtrace.database import BackendType, UnifiedMindtraceODM


db = UnifiedMindtraceODM(
    unified_model_cls=User,
    mongo_db_uri="mongodb://localhost:27017",
    mongo_db_name="myapp",
    redis_url="redis://localhost:6379",
    preferred_backend=BackendType.MONGO,
)
```

### Common operations

```python
# Async operations
inserted_user = await db.insert_async(User(name="Alice", email="alice@example.com", age=30))
retrieved_user = await db.get_async(inserted_user.id)
retrieved_user.age = 31
updated_user = await db.update_async(retrieved_user)
all_users = await db.all_async()
python_users = await db.find_async({"name": "Alice"})
```

```python
# Sync operations
inserted_user = db.insert(User(name="Bob", email="bob@example.com", age=25))
retrieved_user = db.get(inserted_user.id)
retrieved_user.age = 26
updated_user = db.update(retrieved_user)
all_users = db.all()
```

### Switching backends

```python
db.switch_backend(BackendType.REDIS)
redis_user = db.insert(User(name="Carol", email="carol@example.com", age=28))

current_backend = db.get_current_backend_type()
print(current_backend)
```

### Multi-model mode

All ODMs in this package support multi-model mode.

```python
class Address(UnifiedMindtraceDocument):
    street: str
    city: str

    class Meta:
        collection_name = "addresses"
        global_key_prefix = "myapp"


db = UnifiedMindtraceODM(
    unified_models={"user": User, "address": Address},
    mongo_db_uri="mongodb://localhost:27017",
    mongo_db_name="myapp",
    redis_url="redis://localhost:6379",
)

address = await db.address.insert_async(Address(street="123 Main St", city="NYC"))
user = await db.user.insert_async(User(name="Alice", email="alice@example.com", age=30))
users = await db.user.all_async()
```

In multi-model mode, use attribute-based access like `db.user.insert_async(...)` rather than `db.insert_async(...)`.

## MongoMindtraceODM

Use `MongoMindtraceODM` when you want MongoDB-specific document models and Beanie features.

### Mongo document model

```python
from typing import Annotated

from beanie import Indexed

from mindtrace.database import MindtraceDocument


class MongoUser(MindtraceDocument):
    name: str
    email: Annotated[str, Indexed(unique=True)]
    age: int

    class Settings:
        name = "users"
        use_cache = False
```

### Mongo ODM setup

```python
from mindtrace.database import MongoMindtraceODM


db = MongoMindtraceODM(
    model_cls=MongoUser,
    db_uri="mongodb://localhost:27017",
    db_name="myapp",
)
```

### Async-first behavior

MongoDB is natively async in this package.

```python
inserted = await db.insert(MongoUser(name="Alice", email="alice@example.com", age=30))
fetched = await db.get(inserted.id)
results = await db.find(MongoUser.name == "Alice")
```

### Sync wrappers

```python
inserted = db.insert_sync(MongoUser(name="Bob", email="bob@example.com", age=25))
fetched = db.get_sync(inserted.id)
all_users = db.all_sync()
```

### Linked documents

MongoDB supports Beanie `Link` fields.

```python
from typing import Optional

from mindtrace.database import Link, MindtraceDocument, MongoMindtraceODM


class Address(MindtraceDocument):
    street: str
    city: str

    class Settings:
        name = "addresses"
        use_cache = False


class UserWithAddress(MindtraceDocument):
    name: str
    address: Optional[Link[Address]] = None

    class Settings:
        name = "users"
        use_cache = False


db = MongoMindtraceODM(
    models={"user": UserWithAddress, "address": Address},
    db_uri="mongodb://localhost:27017",
    db_name="myapp",
)

address = await db.address.insert(Address(street="123 Main St", city="NYC"))
user = await db.user.insert(UserWithAddress(name="Alice", address=address))
user_with_links = await db.user.get(user.id, fetch_links=True)
```

### Aggregation

```python
pipeline = [
    {"$match": {"age": {"$gte": 18}}},
    {"$group": {"_id": "$age", "count": {"$sum": 1}}},
]
results = await db.aggregate(pipeline)
```

## RedisMindtraceODM

Use `RedisMindtraceODM` when you want Redis-backed JSON documents and indexed Redis OM queries.

### Redis document model

```python
from redis_om import Field

from mindtrace.database import MindtraceRedisDocument


class RedisUser(MindtraceRedisDocument):
    name: str = Field(index=True)
    email: str = Field(index=True)
    age: int = Field(index=True)

    class Meta:
        global_key_prefix = "myapp"
```

### Redis ODM setup

```python
from mindtrace.database import RedisMindtraceODM


db = RedisMindtraceODM(
    model_cls=RedisUser,
    redis_url="redis://localhost:6379",
)
```

### Sync-first behavior

Redis is natively sync in this package.

```python
inserted = db.insert(RedisUser(name="Alice", email="alice@example.com", age=30))
fetched = db.get(inserted.id)
results = db.find(RedisUser.age >= 18)
all_users = db.all()
```

### Async wrappers

```python
inserted = await db.insert_async(RedisUser(name="Bob", email="bob@example.com", age=25))
fetched = await db.get_async(inserted.id)
all_users = await db.all_async()
```

### Notes on Redis IDs

Redis OM uses `pk` internally, but `MindtraceRedisDocument` exposes a consistent `id` property so code can treat MongoDB and Redis documents more similarly.

## RegistryMindtraceODM

Use `RegistryMindtraceODM` when you want a simpler registry-backed ODM using Mindtrace’s Registry layer instead of a database server.

```python
from pydantic import BaseModel

from mindtrace.database import RegistryMindtraceODM


class User(BaseModel):
    name: str
    email: str


db = RegistryMindtraceODM(model_cls=User)
inserted = db.insert(User(name="John Doe", email="john@example.com"))
retrieved = db.get(inserted.id)
retrieved.name = "John Smith"
updated = db.update(retrieved)
all_users = db.all()
```

This backend is useful when you want the ODM interface but prefer Registry-backed storage semantics.

## Sync and Async Interfaces

All ODMs expose the same broad CRUD shape, but their native execution mode differs.

- **MongoMindtraceODM** — native async, with sync wrappers
- **RedisMindtraceODM** — native sync, with async wrappers
- **UnifiedMindtraceODM** — routes to the active backend and adapts accordingly
- **RegistryMindtraceODM** — sync-oriented

That means you can often keep the same mental model while fitting your application’s execution style.

## Initialization

ODMs support automatic or explicit initialization.

```python
from mindtrace.database import BackendType, InitMode, UnifiedMindtraceDocument, UnifiedMindtraceODM


db = UnifiedMindtraceODM(
    unified_model_cls=User,
    mongo_db_uri="mongodb://localhost:27017",
    mongo_db_name="myapp",
    redis_url="redis://localhost:6379",
    preferred_backend=BackendType.MONGO,
    auto_init=True,
    init_mode=InitMode.SYNC,
)
```

### Init modes

- `InitMode.SYNC`
- `InitMode.ASYNC`

Defaults differ by backend:

- MongoDB defaults to `ASYNC`
- Redis defaults to `SYNC`
- Registry is sync-oriented

## Error Handling

The package provides a consistent exception surface across backends.

```python
from mindtrace.database import DocumentNotFoundError, DuplicateInsertError


try:
    user = await db.get_async("missing-id")
except DocumentNotFoundError as e:
    print(f"Not found: {e}")

try:
    await db.insert_async(User(name="Alice", email="alice@example.com", age=30))
except DuplicateInsertError as e:
    print(f"Duplicate insert: {e}")
```

In multi-model mode, calling direct methods like `db.insert(...)` instead of `db.user.insert(...)` raises a `ValueError` to prevent ambiguity.

## Installation

If you are working from the full Mindtrace repo:

```bash
$ git clone https://github.com/Mindtrace/mindtrace.git && cd mindtrace
$ uv sync --dev --all-extras
```

The database package depends on backend libraries such as Beanie, Motor, PyMongo, and Redis OM.

## Examples

Related examples in the repo:

- [Unified ODM example](../../samples/database/unified_example.py)
- [MongoDB example](../../samples/database/mongo_example.py)
- [Redis example](../../samples/database/redis_example.py)
- [Registry example](../../samples/database/registry_example.py)
- [Database samples README](../../samples/database/README.md)

## Testing

If you are working in the full Mindtrace repo, run tests for this module specifically:

```bash
$ git clone https://github.com/Mindtrace/mindtrace.git && cd mindtrace
$ uv sync --dev --all-extras
$ ds test: database
$ ds test: --unit database
```

If you want backend-specific integration coverage as well:

```bash
$ ds test: database --integration
```

## Practical Notes and Caveats

- `UnifiedMindtraceODM` only exposes the overlap of capabilities that make sense across MongoDB and Redis; backend-specific features still live on the backend-specific ODMs.
- Multi-model mode changes the calling style: use attribute-based access like `db.user.get(...)`.
- MongoDB supports linked documents and aggregation; Redis does not provide the same feature set.
- Redis and MongoDB differ in native execution style, so some methods are wrappers around the backend’s natural sync/async mode.
- `RegistryMindtraceODM` is useful for simpler or storage-backed workflows, but its query capabilities are intentionally simpler than MongoDB or Redis.

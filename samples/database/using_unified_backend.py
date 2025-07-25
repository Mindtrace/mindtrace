"""
Sample usage of the UnifiedMindtraceODMBackend.

This example demonstrates how to use the unified backend to work with both
MongoDB and Redis databases using a common interface.
"""

import asyncio
from typing import Annotated

from beanie import Indexed
from pydantic import BaseModel, Field

from mindtrace.database import (
    BackendType,
    DocumentNotFoundError,
    DuplicateInsertError,
    MindtraceDocument,
    MindtraceRedisDocument,
    UnifiedMindtraceDocument,
    UnifiedMindtraceODMBackend,
)

# Configuration
MONGO_URI = "mongodb://localhost:27017"
MONGO_DB_NAME = "unified_sample_db"
REDIS_URL = "redis://localhost:6379"

# Define our data models
class UserCreate(BaseModel):
    name: str
    age: int
    email: str
    skills: list[str] = []

# Unified model that works with both backends - Super Simple!
class UnifiedUserDoc(UnifiedMindtraceDocument):
    name: str = Field(description="User's full name")
    age: int = Field(ge=0, le=150, description="User's age")
    email: str = Field(description="User's email address")
    skills: list[str] = Field(default_factory=list, description="User's skills")
    
    class Meta:
        collection_name = "users"
        global_key_prefix = "sample"
        use_cache = False
        indexed_fields = ["name", "age", "email", "skills"]
        unique_fields = ["email"]

# Legacy models for backward compatibility
class MongoUserDoc(MindtraceDocument):
    name: str
    age: int
    email: Annotated[str, Indexed(unique=True)]
    skills: list[str] = []

    class Settings:
        name = "users"
        use_cache = False

class RedisUserDoc(MindtraceRedisDocument):
    name: str = Field(index=True)
    age: int = Field(index=True)
    email: str = Field(index=True)
    skills: list[str] = Field(index=True, default_factory=list)

    class Meta:
        global_key_prefix = "sample"

async def demonstrate_mongo_backend():
    """Demonstrate using the unified backend with MongoDB."""
    print("\n=== MongoDB Backend Demonstration ===")
    
    # Create unified backend with only MongoDB
    backend = UnifiedMindtraceODMBackend(
        mongo_model_cls=MongoUserDoc,
        mongo_db_uri=MONGO_URI,
        mongo_db_name=MONGO_DB_NAME,
        preferred_backend=BackendType.MONGO
    )
    
    # Clean up any existing data
    await backend.initialize_async()
    mongo_backend = backend.get_mongo_backend()
    await mongo_backend.model_cls.delete_all()
    
    print(f"Current backend: {backend.get_current_backend_type()}")
    print(f"Is async: {backend.is_async()}")
    
    # Create some sample users
    users = [
        UserCreate(name="Alice", age=30, email="alice@example.com", skills=["Python", "MongoDB"]),
        UserCreate(name="Bob", age=25, email="bob@example.com", skills=["JavaScript", "Redis"]),
        UserCreate(name="Charlie", age=35, email="charlie@example.com", skills=["Python", "Docker"]),
    ]
    
    # Insert users
    print("\nInserting users...")
    inserted_users = []
    for user in users:
        try:
            inserted = await backend.insert_async(user)
            inserted_users.append(inserted)
            print(f"Inserted: {inserted.name} (ID: {inserted.id})")
        except DuplicateInsertError as e:
            print(f"Duplicate insert error: {e}")
    
    # Get all users
    print("\nRetrieving all users...")
    all_users = await backend.all_async()
    for user in all_users:
        print(f"User: {user.name}, Age: {user.age}, Email: {user.email}")
    
    # Find users by criteria
    print("\nFinding users with age >= 30...")
    mature_users = await backend.find_async({"age": {"$gte": 30}})
    for user in mature_users:
        print(f"Mature user: {user.name}, Age: {user.age}")
    
    # Get a specific user
    if inserted_users:
        user_id = str(inserted_users[0].id)
        print(f"\nRetrieving user with ID: {user_id}")
        try:
            specific_user = await backend.get_async(user_id)
            print(f"Retrieved: {specific_user.name}, Email: {specific_user.email}")
        except DocumentNotFoundError as e:
            print(f"User not found: {e}")
    
    # Clean up
    print("\nCleaning up...")
    for user in inserted_users:
        await backend.delete_async(str(user.id))
    print("MongoDB demonstration completed!")

def demonstrate_redis_backend():
    """Demonstrate using the unified backend with Redis."""
    print("\n=== Redis Backend Demonstration ===")
    
    # Create unified backend with only Redis
    backend = UnifiedMindtraceODMBackend(
        redis_model_cls=RedisUserDoc,
        redis_url=REDIS_URL,
        preferred_backend=BackendType.REDIS
    )
    
    # Clean up any existing data
    backend.initialize_sync()
    redis_backend = backend.get_redis_backend()
    pattern = f"{RedisUserDoc.Meta.global_key_prefix}:*"
    keys = redis_backend.redis.keys(pattern)
    if keys:
        redis_backend.redis.delete(*keys)
    
    print(f"Current backend: {backend.get_current_backend_type()}")
    print(f"Is async: {backend.is_async()}")
    
    # Create some sample users
    users = [
        UserCreate(name="Dave", age=28, email="dave@example.com", skills=["Redis", "Python"]),
        UserCreate(name="Eve", age=32, email="eve@example.com", skills=["Docker", "Kubernetes"]),
        UserCreate(name="Frank", age=27, email="frank@example.com", skills=["JavaScript", "Node.js"]),
    ]
    
    # Insert users
    print("\nInserting users...")
    inserted_users = []
    for user in users:
        try:
            inserted = backend.insert(user)
            inserted_users.append(inserted)
            print(f"Inserted: {inserted.name} (PK: {inserted.pk})")
        except DuplicateInsertError as e:
            print(f"Duplicate insert error: {e}")
    
    # Get all users
    print("\nRetrieving all users...")
    all_users = backend.all()
    for user in all_users:
        print(f"User: {user.name}, Age: {user.age}, Email: {user.email}")
    
    # Find users by criteria
    print("\nFinding users with age >= 30...")
    mature_users = backend.find(RedisUserDoc.age >= 30)
    for user in mature_users:
        print(f"Mature user: {user.name}, Age: {user.age}")
    
    # Get a specific user
    if inserted_users:
        user_pk = inserted_users[0].pk
        print(f"\nRetrieving user with PK: {user_pk}")
        try:
            specific_user = backend.get(user_pk)
            print(f"Retrieved: {specific_user.name}, Email: {specific_user.email}")
        except DocumentNotFoundError as e:
            print(f"User not found: {e}")
    
    # Clean up
    print("\nCleaning up...")
    for user in inserted_users:
        backend.delete(user.pk)
    print("Redis demonstration completed!")

async def demonstrate_dual_backend():
    """Demonstrate using the unified backend with both MongoDB and Redis."""
    print("\n=== Dual Backend Demonstration ===")
    
    # Create unified backend with both MongoDB and Redis
    backend = UnifiedMindtraceODMBackend(
        mongo_model_cls=MongoUserDoc,
        mongo_db_uri=MONGO_URI,
        mongo_db_name=MONGO_DB_NAME,
        redis_model_cls=RedisUserDoc,
        redis_url=REDIS_URL,
        preferred_backend=BackendType.MONGO  # Start with MongoDB
    )
    
    # Clean up both backends
    await backend.initialize_async()
    backend.initialize_sync()
    
    # Clean MongoDB
    mongo_backend = backend.get_mongo_backend()
    await mongo_backend.model_cls.delete_all()
    
    # Clean Redis
    redis_backend = backend.get_redis_backend()
    pattern = f"{RedisUserDoc.Meta.global_key_prefix}:*"
    keys = redis_backend.redis.keys(pattern)
    if keys:
        redis_backend.redis.delete(*keys)
    
    print(f"Has MongoDB: {backend.has_mongo_backend()}")
    print(f"Has Redis: {backend.has_redis_backend()}")
    
    # Start with MongoDB
    print(f"\nCurrent backend: {backend.get_current_backend_type()}")
    mongo_user = UserCreate(name="MongoDB User", age=30, email="mongo@example.com")
    mongo_inserted = await backend.insert_async(mongo_user)
    print(f"Inserted to MongoDB: {mongo_inserted.name}")
    
    # Switch to Redis
    backend.switch_backend(BackendType.REDIS)
    print(f"\nSwitched to backend: {backend.get_current_backend_type()}")
    redis_user = UserCreate(name="Redis User", age=25, email="redis@example.com")
    redis_inserted = await backend.insert_async(redis_user)
    print(f"Inserted to Redis: {redis_inserted.name}")
    
    # Verify data isolation
    print("\nVerifying data isolation...")
    
    # Check MongoDB data
    backend.switch_backend(BackendType.MONGO)
    mongo_all = await backend.all_async()
    print(f"MongoDB has {len(mongo_all)} users:")
    for user in mongo_all:
        print(f"  - {user.name}")
    
    # Check Redis data
    backend.switch_backend(BackendType.REDIS)
    redis_all = await backend.all_async()
    print(f"Redis has {len(redis_all)} users:")
    for user in redis_all:
        print(f"  - {user.name}")
    
    # Clean up both backends
    print("\nCleaning up...")
    backend.switch_backend(BackendType.MONGO)
    await backend.delete_async(str(mongo_inserted.id))
    
    backend.switch_backend(BackendType.REDIS)
    await backend.delete_async(redis_inserted.pk)
    
    print("Dual backend demonstration completed!")

async def demonstrate_async_compatibility():
    """Demonstrate async compatibility with both backends."""
    print("\n=== Async Compatibility Demonstration ===")
    
    # Create Redis backend (normally sync)
    redis_backend = UnifiedMindtraceODMBackend(
        redis_model_cls=RedisUserDoc,
        redis_url=REDIS_URL,
        preferred_backend=BackendType.REDIS
    )
    
    # Clean up
    redis_backend.initialize_sync()
    backend_instance = redis_backend.get_redis_backend()
    pattern = f"{RedisUserDoc.Meta.global_key_prefix}:*"
    keys = backend_instance.redis.keys(pattern)
    if keys:
        backend_instance.redis.delete(*keys)
    
    print("Using Redis backend with async interface...")
    
    # Use async methods with Redis (should work transparently)
    user = UserCreate(name="Async User", age=28, email="async@example.com")
    
    # Async operations on sync backend
    inserted = await redis_backend.insert_async(user)
    print(f"Async inserted: {inserted.name}")
    
    fetched = await redis_backend.get_async(inserted.pk)
    print(f"Async fetched: {fetched.name}")
    
    all_users = await redis_backend.all_async()
    print(f"Async all: {len(all_users)} users")
    
    found_users = await redis_backend.find_async(RedisUserDoc.name == "Async User")
    print(f"Async found: {len(found_users)} users")
    
    # Clean up
    await redis_backend.delete_async(inserted.pk)
    print("Async compatibility demonstration completed!")

async def demonstrate_unified_document_model():
    """Demonstrate using the unified document model."""
    print("\n=== Unified Document Model Demonstration ===")
    
    # Create unified backend with unified model
    backend = UnifiedMindtraceODMBackend(
        unified_model_cls=UnifiedUserDoc,
        mongo_db_uri=MONGO_URI,
        mongo_db_name=MONGO_DB_NAME,
        redis_url=REDIS_URL,
        preferred_backend=BackendType.MONGO
    )
    
    # Clean up both backends
    await backend.initialize_async()
    backend.initialize_sync()
    
    # Clean MongoDB
    if backend.has_mongo_backend():
        mongo_backend = backend.get_mongo_backend()
        await mongo_backend.model_cls.delete_all()
    
    # Clean Redis
    if backend.has_redis_backend():
        redis_backend = backend.get_redis_backend()
        pattern = f"{UnifiedUserDoc.get_meta().global_key_prefix}:*"
        keys = redis_backend.redis.keys(pattern)
        if keys:
            redis_backend.redis.delete(*keys)
    
    print(f"Using unified model: {backend.get_unified_model().__name__}")
    print(f"Current backend: {backend.get_current_backend_type()}")
    
    # Create unified document instances
    unified_user1 = UnifiedUserDoc(
        name="Unified User 1",
        age=28,
        email="unified1@example.com",
        skills=["Python", "MongoDB", "Redis"]
    )
    
    unified_user2 = UnifiedUserDoc(
        name="Unified User 2",
        age=32,
        email="unified2@example.com",
        skills=["JavaScript", "Docker", "Kubernetes"]
    )
    
    # Test with MongoDB backend
    print("\n--- Testing with MongoDB ---")
    backend.switch_backend(BackendType.MONGO)
    print(f"Current backend: {backend.get_current_backend_type()}")
    
    # Insert unified documents
    mongo_inserted1 = await backend.insert_async(unified_user1)
    mongo_inserted2 = await backend.insert_async(unified_user2)
    print(f"Inserted: {mongo_inserted1.name} and {mongo_inserted2.name}")
    
    # Retrieve all users
    mongo_all = await backend.all_async()
    print(f"MongoDB has {len(mongo_all)} users")
    
    # Test with Redis backend
    print("\n--- Testing with Redis ---")
    backend.switch_backend(BackendType.REDIS)
    print(f"Current backend: {backend.get_current_backend_type()}")
    
    # Insert the same unified documents (different backend)
    redis_inserted1 = await backend.insert_async(unified_user1)
    redis_inserted2 = await backend.insert_async(unified_user2)
    print(f"Inserted: {redis_inserted1.name} and {redis_inserted2.name}")
    
    # Retrieve all users
    redis_all = await backend.all_async()
    print(f"Redis has {len(redis_all)} users")
    
    # Demonstrate data isolation
    print("\n--- Data Isolation ---")
    backend.switch_backend(BackendType.MONGO)
    mongo_final = await backend.all_async()
    backend.switch_backend(BackendType.REDIS)
    redis_final = await backend.all_async()
    
    print(f"MongoDB users: {[u.name for u in mongo_final]}")
    print(f"Redis users: {[u.name for u in redis_final]}")
    print("✓ Data is properly isolated between backends")
    
    # Clean up
    print("\n--- Cleanup ---")
    backend.switch_backend(BackendType.MONGO)
    await backend.delete_async(str(mongo_inserted1.id))
    await backend.delete_async(str(mongo_inserted2.id))
    
    backend.switch_backend(BackendType.REDIS)
    await backend.delete_async(redis_inserted1.pk)
    await backend.delete_async(redis_inserted2.pk)
    
    print("Unified document model demonstration completed!")

async def main():
    """Run all demonstrations."""
    print("UnifiedMindtraceODMBackend Demonstrations")
    print("=" * 50)
    
    try:
        # Demonstrate unified document model
        await demonstrate_unified_document_model()
        
        # Demonstrate MongoDB backend
        await demonstrate_mongo_backend()
        
        # Demonstrate Redis backend
        demonstrate_redis_backend()
        
        # Demonstrate dual backend
        await demonstrate_dual_backend()
        
        # Demonstrate async compatibility
        await demonstrate_async_compatibility()
        
    except Exception as e:
        print(f"\nError during demonstration: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 50)
    print("All demonstrations completed!")

if __name__ == "__main__":
    # Run the demonstrations
    asyncio.run(main()) 
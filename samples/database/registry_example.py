#!/usr/bin/env python3
"""
Registry ODM Example

Demonstrates using RegistryMindtraceODM with the Mindtrace Registry system.
Supports local storage, GCP storage, and other storage backends.

Prerequisites:
- mindtrace-registry module installed
"""

from pathlib import Path
from typing import Any, Type

from pydantic import BaseModel

from mindtrace.database import DocumentNotFoundError, RegistryMindtraceODM
from mindtrace.registry import Archiver, Registry

# ============================================================================
# Model Definitions
# ============================================================================


class User(BaseModel):
    """User model for Registry ODM."""

    name: str
    email: str
    age: int = 0


class Address(BaseModel):
    """Address model for Registry ODM."""

    street: str
    city: str
    state: str
    zip_code: str


# ============================================================================
# Archiver Implementations
# ============================================================================


class UserArchiver(Archiver):
    """Archiver for User model - saves to JSON files."""

    def save(self, user: User):
        """Save user to JSON file."""
        file_path = Path(self.uri) / f"user_{user.email.replace('@', '_at_')}.json"
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w") as f:
            f.write(user.model_dump_json())

    def load(self, data_type: Type[Any]) -> User:
        """Load user from JSON file."""
        # In a real implementation, you'd need to know which file to load
        # This is a simplified example
        files = list(Path(self.uri).glob("user_*.json"))
        if files:
            with open(files[0], "r") as f:
                return User.model_validate_json(f.read())
        raise FileNotFoundError("User file not found")


class AddressArchiver(Archiver):
    """Archiver for Address model - saves to JSON files."""

    def save(self, address: Address):
        """Save address to JSON file."""
        file_path = Path(self.uri) / f"address_{address.zip_code}.json"
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w") as f:
            f.write(address.model_dump_json())

    def load(self, data_type: Type[Any]) -> Address:
        """Load address from JSON file."""
        files = list(Path(self.uri).glob("address_*.json"))
        if files:
            with open(files[0], "r") as f:
                return Address.model_validate_json(f.read())
        raise FileNotFoundError("Address file not found")


# ============================================================================
# Example Functions
# ============================================================================


def demonstrate_single_model():
    """Demonstrate Registry ODM with single model."""
    print("\n" + "=" * 70)
    print("REGISTRY ODM - SINGLE MODEL MODE")
    print("=" * 70)

    # Register the archiver for User model
    Registry.register_default_materializer(User, UserArchiver)

    # Initialize Registry ODM
    db = RegistryMindtraceODM(model_cls=User)

    print("✓ Initialized Registry ODM with User model")

    # CREATE - Insert operations
    print("\n--- CREATE Operations ---")

    user = User(name="John Doe", email="john.doe@example.com", age=30)
    inserted_user = db.insert(user)
    print(f"✓ Created user: {inserted_user.name} (ID: {inserted_user.id})")

    # READ - Retrieve operations
    print("\n--- READ Operations ---")

    try:
        retrieved_user = db.get(inserted_user.id)
        print(f"✓ Retrieved user: {retrieved_user.name}, email: {retrieved_user.email}")
    except DocumentNotFoundError:
        print("✗ User not found")

    all_users = db.all()
    print(f"✓ Total users: {len(all_users)}")

    # UPDATE - Update operations
    print("\n--- UPDATE Operations ---")

    inserted_user.name = "John Smith"
    inserted_user.age = 31
    updated_user = db.update(inserted_user)
    print(f"✓ Updated user: {updated_user.name}, age: {updated_user.age}")

    # DELETE - Delete operations
    print("\n--- DELETE Operations ---")

    db.delete(inserted_user.id)
    print("✓ Deleted user")

    print("\n✓ Single model demonstration completed!")


def demonstrate_multi_model():
    """Demonstrate Registry ODM with multiple models."""
    print("\n" + "=" * 70)
    print("REGISTRY ODM - MULTI-MODEL MODE")
    print("=" * 70)

    # Register archivers for both models
    Registry.register_default_materializer(User, UserArchiver)
    Registry.register_default_materializer(Address, AddressArchiver)

    # Initialize Registry ODM with multiple models
    db = RegistryMindtraceODM(models={"user": User, "address": Address})

    print(f"✓ Initialized Registry ODM with {len(db._models)} models")

    # CREATE - Insert operations
    print("\n--- CREATE Operations ---")

    address = Address(
        street="123 Main St",
        city="San Francisco",
        state="CA",
        zip_code="94102",
    )
    inserted_address = db.address.insert(address)
    print(f"✓ Created address: {inserted_address.street}, {inserted_address.city} (ID: {inserted_address.id})")

    user = User(name="Alice Johnson", email="alice@example.com", age=30)
    inserted_user = db.user.insert(user)
    print(f"✓ Created user: {inserted_user.name} (ID: {inserted_user.id})")

    # READ - Retrieve operations
    print("\n--- READ Operations ---")

    retrieved_user = db.user.get(inserted_user.id)
    print(f"✓ Retrieved user: {retrieved_user.name}")

    retrieved_address = db.address.get(inserted_address.id)
    print(f"✓ Retrieved address: {retrieved_address.street}")

    all_users = db.user.all()
    all_addresses = db.address.all()
    print(f"✓ Total users: {len(all_users)}, Total addresses: {len(all_addresses)}")

    # UPDATE - Update operations
    print("\n--- UPDATE Operations ---")

    retrieved_user.age = 31
    updated_user = db.user.update(retrieved_user)
    print(f"✓ Updated user: {updated_user.name}, age: {updated_user.age}")

    # DELETE - Delete operations
    print("\n--- DELETE Operations ---")

    db.user.delete(inserted_user.id)
    db.address.delete(inserted_address.id)
    print("✓ Cleaned up")

    print("\n✓ Multi-model demonstration completed!")


def demonstrate_error_handling():
    """Demonstrate error handling with Registry ODM."""
    print("\n" + "=" * 70)
    print("REGISTRY ODM - ERROR HANDLING")
    print("=" * 70)

    Registry.register_default_materializer(User, UserArchiver)

    db = RegistryMindtraceODM(model_cls=User)

    # DocumentNotFoundError
    print("\n--- Handling DocumentNotFoundError ---")
    try:
        db.get("non_existent_id")
    except DocumentNotFoundError as e:
        print(f"✓ Caught DocumentNotFoundError: {e}")

    print("\n✓ Error handling demonstration completed!")


def main():
    """Run all Registry ODM demonstrations."""
    print("\n" + "=" * 70)
    print("REGISTRY ODM EXAMPLE")
    print("=" * 70)
    print("\nThis example demonstrates:")
    print("  • Single model mode")
    print("  • Multi-model mode")
    print("  • Custom archiver implementation")
    print("  • Error handling")
    print("  • CRUD operations")

    try:
        # Demonstrate single model
        demonstrate_single_model()

        # Demonstrate multi-model
        demonstrate_multi_model()

        # Demonstrate error handling
        demonstrate_error_handling()

        print("\n" + "=" * 70)
        print("ALL REGISTRY ODM DEMONSTRATIONS COMPLETED!")
        print("=" * 70)

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()

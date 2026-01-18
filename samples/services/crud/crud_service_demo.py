#!/usr/bin/env python3
"""
CRUD Service Demo - Demonstrates how to use the CRUD service.

This script shows:
1. Creating items
2. Reading items
3. Updating items
4. Deleting items
5. Listing all items
6. Searching items
7. Both sync and async usage
"""

import asyncio
import traceback

import requests
from crud_service import CRUDService
from fastapi import HTTPException


def sync_crud_example():
    """Demonstrate synchronous CRUD operations."""
    print("=" * 60)
    print("SYNCHRONOUS CRUD OPERATIONS DEMO")
    print("=" * 60)

    # Launch the service
    print("\n1. Launching CRUD Service...")
    cm = CRUDService.launch(port=8080, host="localhost", wait_for_launch=True, timeout=30)
    print(f"   Service running at: {cm.url}")

    try:
        # CREATE - Add some items
        print("\n2. Creating items...")
        item1 = cm.create_item(
            name="Laptop",
            description="High-performance laptop",
            price=1299.99,
            category="Electronics",
        )
        print(f"   Created: {item1.name} (ID: {item1.id})")

        item2 = cm.create_item(
            name="Coffee Maker",
            description="Automatic drip coffee maker",
            price=89.99,
            category="Appliances",
        )
        print(f"   Created: {item2.name} (ID: {item2.id})")

        item3 = cm.create_item(
            name="Desk Chair",
            description="Ergonomic office chair",
            price=299.99,
            category="Furniture",
        )
        print(f"   Created: {item3.name} (ID: {item3.id})")

        # READ - Get an item
        print("\n3. Reading an item...")
        retrieved = cm.get_item(item_id=item1.id)
        print(f"   Retrieved: {retrieved.name} - ${retrieved.price}")

        # UPDATE - Update an item
        print("\n4. Updating an item...")
        updated = cm.update_item(
            item_id=item1.id,
            price=1199.99,
            description="Updated: High-performance laptop on sale",
        )
        print(f"   Updated: {updated.name} - New price: ${updated.price}")
        print(f"   Description: {updated.description}")

        # LIST - List all items
        print("\n5. Listing all items...")
        all_items = cm.list_items()
        print(f"   Total items: {all_items.total}")
        for item in all_items.items:
            print(f"   - {item.name} (${item.price}) - {item.category}")

        # SEARCH - Search items
        print("\n6. Searching items...")
        search_results = cm.search_items(query="laptop", limit=5)
        print(f"   Found {search_results.total} items matching 'laptop'")
        for item in search_results.items:
            print(f"   - {item.name} (${item.price})")

        # Search by category
        print("\n7. Searching by category...")
        category_results = cm.search_items(category="Electronics", limit=10)
        print(f"   Found {category_results.total} items in Electronics category")
        for item in category_results.items:
            print(f"   - {item.name} (${item.price})")

        # Search by price range
        print("\n8. Searching by price range...")
        price_results = cm.search_items(min_price=100.0, max_price=500.0, limit=10)
        print(f"   Found {price_results.total} items between $100 and $500")
        for item in price_results.items:
            print(f"   - {item.name} (${item.price})")

        # DELETE - Delete an item
        print("\n9. Deleting an item...")
        deleted = cm.delete_item(item_id=item2.id)
        print(f"   Deleted: {deleted.name}")

        # Verify deletion
        print("\n10. Verifying deletion...")
        remaining = cm.list_items()
        print(f"   Remaining items: {remaining.total}")
        for item in remaining.items:
            print(f"   - {item.name}")

    except (
        requests.exceptions.RequestException,
        HTTPException,
        RuntimeError,
        ConnectionError,
        TimeoutError,
    ) as e:
        print(f"\nError: {e}")
        traceback.print_exc()

    finally:
        print("\n11. Shutting down service...")
        cm.shutdown()
        print("   Service shutdown complete")


async def async_crud_example():
    """Demonstrate asynchronous CRUD operations."""
    print("\n" + "=" * 60)
    print("ASYNCHRONOUS CRUD OPERATIONS DEMO")
    print("=" * 60)

    # Launch the service
    print("\n1. Launching CRUD Service...")
    cm = CRUDService.launch(port=8081, host="localhost", wait_for_launch=True, timeout=30)
    print(f"   Service running at: {cm.url}")

    try:
        # CREATE - Add items concurrently
        print("\n2. Creating items concurrently...")
        tasks = [
            cm.acreate_item(
                name=f"Item {i}",
                description=f"Description for item {i}",
                price=float(10 * i),
                category="Test",
            )
            for i in range(1, 6)
        ]
        items = await asyncio.gather(*tasks)
        print(f"   Created {len(items)} items concurrently")
        for item in items:
            print(f"   - {item.name} (ID: {item.id})")

        # READ - Read items concurrently
        print("\n3. Reading items concurrently...")
        read_tasks = [cm.aget_item(item_id=item.id) for item in items[:3]]
        read_results = await asyncio.gather(*read_tasks)
        print(f"   Read {len(read_results)} items concurrently")
        for item in read_results:
            print(f"   - {item.name} (${item.price})")

        # LIST - List all items
        print("\n4. Listing all items...")
        all_items = await cm.alist_items()
        print(f"   Total items: {all_items.total}")

        # SEARCH - Search items
        print("\n5. Searching items...")
        search_results = await cm.asearch_items(query="Item", limit=10)
        print(f"   Found {search_results.total} items matching 'Item'")

    except (
        requests.exceptions.RequestException,
        HTTPException,
        RuntimeError,
        ConnectionError,
        TimeoutError,
    ) as e:
        print(f"\nError: {e}")
        traceback.print_exc()

    finally:
        print("\n6. Shutting down service...")
        await cm.ashutdown()
        print("   Service shutdown complete")


def main():
    """Run all CRUD examples."""
    print("\n" + "=" * 60)
    print("CRUD SERVICE DEMONSTRATION")
    print("=" * 60)

    # Run sync example
    sync_crud_example()

    # Run async example
    asyncio.run(async_crud_example())

    print("\n" + "=" * 60)
    print("ALL DEMOS COMPLETED")
    print("=" * 60)


if __name__ == "__main__":
    main()

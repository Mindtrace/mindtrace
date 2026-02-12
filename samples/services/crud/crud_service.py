#!/usr/bin/env python3
"""
CRUD Service Example - Demonstrates Create, Read, Update, Delete operations.

This service shows how to build a complete CRUD API using mindtrace-services
with an in-memory dictionary for storage.
"""

from datetime import UTC, datetime
from typing import Optional
from uuid import uuid4

from fastapi import HTTPException
from pydantic import BaseModel

from mindtrace.core import TaskSchema
from mindtrace.services import Service

# ============================================================================
# Data Models
# ============================================================================


class ItemCreateInput(BaseModel):
    """Input model for creating an item."""

    name: str
    description: Optional[str] = None
    price: float
    category: str


class ItemUpdateInput(BaseModel):
    """Input model for updating an item."""

    item_id: str
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    category: Optional[str] = None


class ItemOutput(BaseModel):
    """Output model for an item."""

    id: str
    name: str
    description: Optional[str]
    price: float
    category: str
    created_at: str
    updated_at: str


class ItemIDInput(BaseModel):
    """Input model for operations requiring an item ID."""

    item_id: str


class ItemListOutput(BaseModel):
    """Output model for listing items."""

    items: list[ItemOutput]
    total: int


class ItemSearchInput(BaseModel):
    """Input model for searching items."""

    query: Optional[str] = None
    category: Optional[str] = None
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    limit: int = 10
    offset: int = 0


# ============================================================================
# Task Schemas
# ============================================================================

create_item_schema = TaskSchema(
    name="create_item",
    input_schema=ItemCreateInput,
    output_schema=ItemOutput,
)

get_item_schema = TaskSchema(
    name="get_item",
    input_schema=None,  # Uses query parameter: item_id
    output_schema=ItemOutput,
)

update_item_schema = TaskSchema(
    name="update_item",
    input_schema=ItemUpdateInput,
    output_schema=ItemOutput,
)

delete_item_schema = TaskSchema(
    name="delete_item",
    input_schema=None,  # Uses query parameter: item_id
    output_schema=ItemOutput,
)

list_items_schema = TaskSchema(
    name="list_items",
    input_schema=None,  # No input required
    output_schema=ItemListOutput,
)

search_items_schema = TaskSchema(
    name="search_items",
    input_schema=None,  # Uses query parameters: query, category, min_price, max_price, limit, offset
    output_schema=ItemListOutput,
)


# ============================================================================
# CRUD Service
# ============================================================================


class CRUDService(Service):
    """Service demonstrating CRUD operations with in-memory storage."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # In-memory storage dictionary
        # Format: {item_id: {item_data}}
        self._items: dict[str, dict] = {}

        # Register all CRUD endpoints with appropriate HTTP methods
        self.add_endpoint(
            "create_item",
            self.create_item,
            schema=create_item_schema,
            methods=["POST"],
        )
        self.add_endpoint(
            "get_item",
            self.get_item,
            schema=get_item_schema,
            methods=["GET"],
        )
        self.add_endpoint(
            "update_item",
            self.update_item,
            schema=update_item_schema,
            methods=["PUT"],
        )
        self.add_endpoint(
            "delete_item",
            self.delete_item,
            schema=delete_item_schema,
            methods=["DELETE"],
        )
        self.add_endpoint(
            "list_items",
            self.list_items,
            schema=list_items_schema,
            methods=["GET"],
        )
        self.add_endpoint(
            "search_items",
            self.search_items,
            schema=search_items_schema,
            methods=["GET"],
        )

    def create_item(self, payload: ItemCreateInput) -> ItemOutput:
        """Create a new item.

        Args:
            payload: Item creation data

        Returns:
            Created item with generated ID and timestamps
        """
        item_id = str(uuid4())
        now = datetime.now(UTC).isoformat()

        item_data = {
            "id": item_id,
            "name": payload.name,
            "description": payload.description,
            "price": payload.price,
            "category": payload.category,
            "created_at": now,
            "updated_at": now,
        }

        self._items[item_id] = item_data

        return ItemOutput(**item_data)

    def get_item(self, item_id: str) -> ItemOutput:
        """Get an item by ID.

        Args:
            item_id: The ID of the item to retrieve

        Returns:
            Item data

        Raises:
            HTTPException: If item not found
        """

        if item_id not in self._items:
            raise HTTPException(status_code=404, detail=f"Item with ID {item_id} not found")

        return ItemOutput(**self._items[item_id])

    def update_item(self, payload: ItemUpdateInput) -> ItemOutput:
        """Update an existing item.

        Args:
            payload: Update data (partial) including item_id

        Returns:
            Updated item data

        Raises:
            HTTPException: If item not found
        """

        if payload.item_id not in self._items:
            raise HTTPException(status_code=404, detail=f"Item with ID {payload.item_id} not found")

        # Update only provided fields
        item_data = self._items[payload.item_id]
        if payload.name is not None:
            item_data["name"] = payload.name
        if payload.description is not None:
            item_data["description"] = payload.description
        if payload.price is not None:
            item_data["price"] = payload.price
        if payload.category is not None:
            item_data["category"] = payload.category

        item_data["updated_at"] = datetime.now(UTC).isoformat()

        return ItemOutput(**item_data)

    def delete_item(self, item_id: str) -> ItemOutput:
        """Delete an item by ID.

        Args:
            item_id: The ID of the item to delete

        Returns:
            Deleted item data

        Raises:
            HTTPException: If item not found
        """

        if item_id not in self._items:
            raise HTTPException(status_code=404, detail=f"Item with ID {item_id} not found")

        item_data = self._items.pop(item_id)
        return ItemOutput(**item_data)

    def list_items(self) -> ItemListOutput:
        """List all items.

        Returns:
            List of all items
        """
        items = [ItemOutput(**item_data) for item_data in self._items.values()]
        return ItemListOutput(items=items, total=len(items))

    def search_items(
        self,
        query: Optional[str] = None,
        category: Optional[str] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        limit: int = 10,
        offset: int = 0,
    ) -> ItemListOutput:
        """Search items with filters.

        Args:
            query: Text to search in name and description
            category: Filter by category
            min_price: Minimum price filter
            max_price: Maximum price filter
            limit: Maximum number of results to return
            offset: Number of results to skip for pagination

        Returns:
            Filtered list of items
        """
        results = []

        for item_data in self._items.values():
            item = ItemOutput(**item_data)
            match = True

            # Text search in name and description
            if query:
                query_lower = query.lower()
                if not (
                    query_lower in item.name.lower() or (item.description and query_lower in item.description.lower())
                ):
                    match = False

            # Category filter
            if category and item.category != category:
                match = False

            # Price range filter
            if min_price is not None and item.price < min_price:
                match = False
            if max_price is not None and item.price > max_price:
                match = False

            if match:
                results.append(item)

        # Apply pagination
        total = len(results)
        paginated_results = results[offset : offset + limit]

        return ItemListOutput(items=paginated_results, total=total)

# CRUD Service Example

A complete example demonstrating how to build a CRUD (Create, Read, Update, Delete) API using the `mindtrace-services` module with in-memory dictionary storage.

## Files

- **`crud_service.py`** - The CRUD service implementation
- **`crud_service_demo.py`** - Demo script showing how to use the service

## Quick Start

### Launch the Service (for Swagger Docs)

To start the service and access Swagger documentation:

```bash
cd samples/services/crud
python run_service.py
```

Then open your browser to:
- **Swagger UI**: http://localhost:8080/docs
- **ReDoc**: http://localhost:8080/redoc

### Run the Demo

```bash
cd samples/services/crud
python crud_service_demo.py
```

This will demonstrate all CRUD operations in both synchronous and asynchronous modes.

## Usage

### Launch the Service

```python
from crud_service import CRUDService

# Launch service on port 8080
cm = CRUDService.launch(port=8080, host="localhost", wait_for_launch=True)
```

### Create an Item

```python
item = cm.create_item(
    name="Laptop",
    description="High-performance laptop",
    price=1299.99,
    category="Electronics"
)
print(f"Created item: {item.id}")
```

### Read an Item

```python
retrieved = cm.get_item(item_id=item.id)
print(f"Item: {retrieved.name} - ${retrieved.price}")
```

### Update an Item

```python
updated = cm.update_item(
    item_id=item.id,
    price=1199.99,
    description="Updated description"
)
```

### Delete an Item

```python
deleted = cm.delete_item(item_id=item.id)
print(f"Deleted: {deleted.name}")
```

### List All Items

```python
all_items = cm.list_items()
print(f"Total items: {all_items.total}")
for item in all_items.items:
    print(f"- {item.name} (${item.price})")
```

### Search Items

```python
# Search by text
results = cm.search_items(query="laptop", limit=10)

# Search by category
results = cm.search_items(category="Electronics", limit=10)

# Search by price range
results = cm.search_items(min_price=100.0, max_price=500.0, limit=10)

# Combined search
results = cm.search_items(
    query="laptop",
    category="Electronics",
    min_price=1000.0,
    max_price=2000.0,
    limit=10,
    offset=0
)
```

### Async Operations

All operations have async versions:

```python
import asyncio

# Async create
item = await cm.acreate_item(name="Item", price=99.99, category="Test")

# Async read
retrieved = await cm.aget_item(item_id=item.id)

# Async update
updated = await cm.aupdate_item(item_id=item.id, price=89.99)

# Async delete
deleted = await cm.adelete_item(item_id=item.id)

# Async list
all_items = await cm.alist_items()

# Async search
results = await cm.asearch_items(query="test", limit=10)
```

## Available Endpoints

- `POST /create_item` - Create a new item
- `GET /get_item` - Get item by ID
- `PUT /update_item` - Update an existing item
- `DELETE /delete_item` - Delete an item
- `GET /list_items` - List all items
- `GET /search_items` - Search items with filters

## Alternative Launch Methods

You can also launch the service directly from Python:

```python
from crud_service import CRUDService

# Launch in blocking mode
CRUDService.launch(host="0.0.0.0", port=8080, block=True)
```

Or use uvicorn directly (if you have the service instance):

```python
import uvicorn
from crud_service import CRUDService

service = CRUDService(host="0.0.0.0", port=8080)
uvicorn.run(service.app, host="0.0.0.0", port=8080)
```

## Notes

- Data is stored in memory and will be lost when the service shuts down
- For production use, replace the in-memory dictionary with a database
- Endpoints use appropriate HTTP methods (GET, POST, PUT, DELETE) following REST conventions
- FastAPI automatically generates interactive API documentation at `/docs` (Swagger UI) and `/redoc`


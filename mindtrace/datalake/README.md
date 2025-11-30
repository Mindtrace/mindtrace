# Mindtrace Datalake

A unified data lake implementation that manages both database-stored and registry-stored data, providing a seamless interface for storing, retrieving, and querying data with support for derivation relationships and complex queries.

## Overview

The Mindtrace Datalake is a core component of the Mindtrace platform that provides a unified interface for managing data regardless of where it's physically stored. It supports both direct database storage for small data and external registry storage for large data, with automatic data loading and caching.

## Features

- **Unified Data Storage**: Store data either directly in MongoDB or in external registry backends
- **Automatic Data Loading**: Registry-stored data is automatically loaded when accessed
- **Derivation Tracking**: Track relationships between data through derivation chains
- **Advanced Querying**: Complex multi-level queries with MongoDB-style filtering
- **Multiple Query Strategies**: Support for "latest", "earliest", "random", and "missing" strategies
- **Flexible Data Formats**: Return data as list of dictionaries or transposed dictionary of lists
- **Registry Caching**: Automatic caching of registry instances for performance
- **Timestamp Tracking**: Automatic `added_at` timestamps for chronological ordering

## Installation

The datalake is part of the Mindtrace platform. Install it as a dependency:

```bash
pip install mindtrace-datalake
```

## Quick Start

```python
from mindtrace.datalake import Datalake

# Initialize the datalake
datalake = Datalake(
    mongo_db_uri="mongodb://localhost:27017",
    mongo_db_name="my_datalake"
)
await datalake.initialize()

# Store data directly in the database
datum = await datalake.add_datum(
    data={"type": "image", "filename": "photo.jpg"},
    metadata={"project": "computer_vision", "tags": ["nature", "outdoor"]}
)

# Store large data in a registry
large_datum = await datalake.add_datum(
    data={"large": "data" * 1000000},  # Large data
    metadata={"project": "big_data"},
    registry_uri="file:///path/to/registry"
)

# Retrieve data (registry data is automatically loaded)
retrieved = await datalake.get_datum(datum.id)
print(retrieved.data)  # Automatically loads registry data if needed
```

## Architecture

### Core Components

#### Datalake Class
The main interface for all datalake operations. Manages both database and registry backends.

#### Datum Model
A unified data structure that can represent data stored in either location:

```python
class Datum:
    data: Any                    # The actual data content
    registry_uri: str | None     # Registry URI if stored externally
    registry_key: str | None     # Key for retrieving from registry
    derived_from: PydanticObjectId | None  # Parent datum ID
    metadata: dict[str, Any]     # Additional metadata
    added_at: datetime          # Timestamp when added
```

### Storage Strategies

#### Database Storage
- **Use Case**: Small to medium data (< 16MB)
- **Benefits**: Fast access, ACID transactions, complex queries
- **Implementation**: Data stored directly in MongoDB

#### Registry Storage
- **Use Case**: Large data (> 16MB), binary files, models
- **Benefits**: Efficient storage, versioning, materialization
- **Implementation**: Data stored in external registry, reference stored in database

## API Reference

### Core Methods

#### `add_datum(data, metadata, registry_uri=None, derived_from=None)`
Add a new datum to the datalake.

**Parameters:**
- `data`: The data to store (any type)
- `metadata`: Dictionary of metadata
- `registry_uri`: Optional registry URI for external storage
- `derived_from`: Optional parent datum ID for derivation tracking

**Returns:** The created `Datum` object with assigned ID

#### `get_datum(datum_id)`
Retrieve a datum by its ID.

**Parameters:**
- `datum_id`: The unique identifier of the datum

**Returns:** The `Datum` object (registry data automatically loaded)

**Raises:** `DocumentNotFoundError` if datum not found

#### `get_data(datum_ids)`
Retrieve multiple data by their IDs.

**Parameters:**
- `datum_ids`: List of datum IDs

**Returns:** List of `Datum` objects

### Derivation Methods

#### `get_directly_derived_data(datum_id)`
Get IDs of data directly derived from the specified datum.

**Parameters:**
- `datum_id`: The parent datum ID

**Returns:** List of child datum IDs

#### `get_indirectly_derived_data(datum_id)`
Get IDs of all data in the derivation chain (breadth-first search).

**Parameters:**
- `datum_id`: The root datum ID

**Returns:** List of all datum IDs in the derivation chain

### Query Methods

#### `query_data(query, datums_wanted=None, transpose=False)`
Query the datalake using MongoDB-style filters with support for multi-level derivation queries.

**Parameters:**
- `query`: Single query dict or list of queries for multi-level queries
- `datums_wanted`: Optional limit on number of results from base query
- `transpose`: If True, returns dict of lists; if False, returns list of dicts

**Returns:** 
- If `transpose=False`: `list[dict[str, Any]]` - List of dictionaries
- If `transpose=True`: `dict[str, list]` - Dictionary of lists

**Query Types:**

1. **Single Query:**
```python
# Find all images in a project
result = await datalake.query_data({
    "metadata.project": "cv_project", 
    "column": "image_id"
})
# Returns: [{"image_id": id1}, {"image_id": id2}, ...]
```

2. **Multi-Query with Derivation:**
```python
# Find images and their classification labels
result = await datalake.query_data([
    {"metadata.project": "cv_project", "column": "image_id"},  # Base query: find images
    {"derived_from": "image_id", "data.type": "classification", "column": "label_id"}  # Derived query: find classifications
])
# Returns: [{"image_id": id1, "label_id": label1}, {"image_id": id2, "label_id": label2}, ...]
```

3. **Complex Filtering:**
```python
# Find images with specific criteria
result = await datalake.query_data({
    "data.type": "image",
    "data.size": {"$gt": 1024},
    "metadata.tags": {"$in": ["nature"]},
    "metadata.quality": {"$gte": 0.9},
    "column": "image_id"
})
```

4. **Query Strategies:**
```python
# Get the latest classification for each image
result = await datalake.query_data([
    {"metadata.project": "cv_project", "column": "image_id"},
    {"derived_from": "image_id", "data.type": "classification", "strategy": "latest", "column": "label_id"}
])

# Get the earliest classification
result = await datalake.query_data([
    {"metadata.project": "cv_project", "column": "image_id"},
    {"derived_from": "image_id", "data.type": "classification", "strategy": "earliest", "column": "label_id"}
])

# Get a random classification
result = await datalake.query_data([
    {"metadata.project": "cv_project", "column": "image_id"},
    {"derived_from": "image_id", "data.type": "classification", "strategy": "random", "column": "label_id"}
])

# Find images that don't have classifications (missing strategy)
result = await datalake.query_data([
    {"metadata.project": "cv_project", "column": "image_id"},
    {"derived_from": "image_id", "data.type": "classification", "strategy": "missing", "column": "label_id"}
])
```

5. **Transposed Results:**
```python
# Get results as dictionary of lists instead of list of dictionaries
result = await datalake.query_data([
    {"metadata.project": "cv_project", "column": "image_id"},
    {"derived_from": "image_id", "data.type": "classification", "column": "label_id"}
], transpose=True)
# Returns: {"image_id": [id1, id2, ...], "label_id": [label1, label2, ...]}
```

6. **Limited Results:**
```python
# Get only the latest 5 images
result = await datalake.query_data({
    "metadata.project": "cv_project", 
    "column": "image_id"
}, datums_wanted=5)
```

## Query Strategies

The datalake supports multiple strategies for selecting data when multiple matches are found:

### Available Strategies

#### `"latest"` (Default)
Selects the datum with the most recent `added_at` timestamp.
```python
# Get the most recent classification for each image
result = await datalake.query_data([
    {"metadata.project": "cv", "column": "image_id"},
    {"derived_from": "image_id", "data.type": "classification", "strategy": "latest", "column": "label_id"}
])
```

#### `"earliest"`
Selects the datum with the oldest `added_at` timestamp.
```python
# Get the first classification for each image
result = await datalake.query_data([
    {"metadata.project": "cv", "column": "image_id"},
    {"derived_from": "image_id", "data.type": "classification", "strategy": "earliest", "column": "label_id"}
])
```

#### `"random"`
Randomly selects one datum from the available matches.
```python
# Get a random classification for each image
result = await datalake.query_data([
    {"metadata.project": "cv", "column": "image_id"},
    {"derived_from": "image_id", "data.type": "classification", "strategy": "random", "column": "label_id"}
])
```

#### `"missing"`
**Subquery only** - Includes the base datum only if no derived data matches the subquery.
```python
# Find images that don't have any classifications
result = await datalake.query_data([
    {"metadata.project": "cv", "column": "image_id"},
    {"derived_from": "image_id", "data.type": "classification", "strategy": "missing", "column": "label_id"}
])
# Returns images without classifications (no label_id column in results)
```

### Data Format and Column Requirements

#### Required `"column"` Key
Every query must include a `"column"` key that specifies the name for the datum ID in the result:
```python
# ✅ Correct - includes column key
query = {"metadata.project": "cv", "column": "image_id"}

# ❌ Incorrect - missing column key
query = {"metadata.project": "cv"}  # Raises ValueError
```

#### Return Formats

**Default Format (List of Dictionaries):**
```python
result = await datalake.query_data([
    {"metadata.project": "cv", "column": "image_id"},
    {"derived_from": "image_id", "data.type": "classification", "column": "label_id"}
])
# Returns: [{"image_id": id1, "label_id": label1}, {"image_id": id2, "label_id": label2}]
```

**Transposed Format (Dictionary of Lists):**
```python
result = await datalake.query_data([
    {"metadata.project": "cv", "column": "image_id"},
    {"derived_from": "image_id", "data.type": "classification", "column": "label_id"}
], transpose=True)
# Returns: {"image_id": [id1, id2], "label_id": [label1, label2]}
```

#### Derivation References
Use column names (strings) for `derived_from`:
```python
# ✅ Correct - uses column name
query = [
    {"metadata.project": "cv", "column": "image_id"},
    {"derived_from": "image_id", "data.type": "classification", "column": "label_id"}
]
```

## Advanced Usage

### Derivation Chains

Track complex data processing pipelines:

```python
# Original image
image = await datalake.add_datum(
    data={"type": "image", "filename": "photo.jpg"},
    metadata={"project": "cv_pipeline"}
)

# Classification
classification = await datalake.add_datum(
    data={"type": "classification", "label": "cat", "confidence": 0.95},
    metadata={"model": "resnet50"},
    derived_from=image.id
)

# Bounding box
bbox = await datalake.add_datum(
    data={"type": "bbox", "x": 10, "y": 20, "width": 100, "height": 80},
    metadata={"model": "yolo"},
    derived_from=classification.id
)

# Query the entire pipeline
pipeline_data = await datalake.query_data([
    {"metadata.project": "cv_pipeline", "column": "image_id"},
    {"derived_from": "image_id", "data.type": "classification", "column": "label_id"},
    {"derived_from": "label_id", "data.type": "bbox", "column": "bbox_id"}
])
# Returns: [{"image_id": img_id, "label_id": label_id, "bbox_id": bbox_id}, ...]
```

### Registry Integration

Store large data efficiently:

```python
# Store a large model
model_datum = await datalake.add_datum(
    data=large_model_object,  # Could be a PyTorch model, large dataset, etc.
    metadata={"model_type": "transformer", "size": "large"},
    registry_uri="s3://my-bucket/models"
)

# Retrieve and use the model
retrieved_model = await datalake.get_datum(model_datum.id)
model = retrieved_model.data  # Automatically loaded from registry
```

### Complex Queries

Find data with sophisticated filtering:

```python
# Find high-quality nature images with recent classifications
result = await datalake.query_data([
    {
        "data.type": "image",
        "metadata.tags": {"$in": ["nature"]},
        "metadata.quality": {"$gte": 0.9},
        "column": "image_id"
    },
    {
        "derived_from": "image_id",
        "data.type": "classification",
        "data.confidence": {"$gte": 0.8},
        "added_at": {"$gte": datetime(2024, 1, 1)},
        "strategy": "latest",
        "column": "label_id"
    }
])
# Returns: [{"image_id": img_id, "label_id": label_id}, ...]

# Get the same data in transposed format
result_transposed = await datalake.query_data([
    {
        "data.type": "image",
        "metadata.tags": {"$in": ["nature"]},
        "metadata.quality": {"$gte": 0.9},
        "column": "image_id"
    },
    {
        "derived_from": "image_id",
        "data.type": "classification",
        "data.confidence": {"$gte": 0.8},
        "strategy": "latest",
        "column": "label_id"
    }
], transpose=True)
# Returns: {"image_id": [img_id1, img_id2, ...], "label_id": [label_id1, label_id2, ...]}
```

## Configuration

### MongoDB Configuration
```python
datalake = Datalake(
    mongo_db_uri="mongodb://username:password@host:port",
    mongo_db_name="datalake_db"
)
```

### Registry Configuration
Supported registry URIs:
- `file:///path/to/local/registry`
- `s3://bucket-name/path`
- `gs://bucket-name/path`
- Custom registry backends

## Performance Considerations

### Registry Caching
- Registry instances are automatically cached by URI
- Reduces connection overhead for repeated operations
- Memory usage scales with number of unique registry URIs

### Query Optimization
- MongoDB indexes on `derived_from` field for fast derivation queries
- Efficient breadth-first search for indirect derivation
- Batch operations for multiple data retrieval

### Storage Recommendations
- Use database storage for: metadata, small data, frequently accessed data
- Use registry storage for: large files, models, datasets, binary data
- Consider data access patterns when choosing storage strategy

## Error Handling

The datalake provides comprehensive error handling:

```python
from mindtrace.database.core.exceptions import DocumentNotFoundError

try:
    datum = await datalake.get_datum(nonexistent_id)
except DocumentNotFoundError:
    print("Datum not found")

try:
    result = await datalake.query_data([
        {"metadata.project": "test", "column": "image_id"},
        {"derived_from": "image_id", "strategy": "invalid", "column": "label_id"}
    ])
except ValueError as e:
    print(f"Invalid query: {e}")

try:
    # Missing strategy not allowed in base query
    result = await datalake.query_data({
        "metadata.project": "test", 
        "strategy": "missing", 
        "column": "image_id"
    })
except ValueError as e:
    print(f"Invalid strategy: {e}")
```

## Contributing

1. Follow the existing code style and patterns
2. Add comprehensive tests for new functionality
3. Update documentation for API changes
4. Ensure 100% test coverage is maintained

## License

Apache License 2.0 - see LICENSE file for details.

## Support

For questions and support:
- GitHub Issues: [mindtrace/mindtrace](https://github.com/mindtrace/mindtrace)
- Documentation: [mindtrace.ai](https://mindtrace.ai)

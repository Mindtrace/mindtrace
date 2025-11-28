# Integration Tests

This directory contains integration tests for the mindtrace registry system, including tests for all supported backends (Local, MinIO, and GCP).

## Test Structure

- `mindtrace/storage/` - Tests for storage handlers (GCS)
- `mindtrace/registry/backend/` - Tests for registry backends (Local, MinIO, GCP)
- `mindtrace/registry/core/` - Tests for registry core functionality

## Prerequisites

### For Local Backend Tests
No additional setup required.

### For MinIO Backend Tests
1. Start a MinIO server:
   ```bash
   docker run --rm --name minio \
     -p 9000:9000 \
     -p 9001:9001 \
     -e MINIO_ROOT_USER=minioadmin \
     -e MINIO_ROOT_PASSWORD=minioadmin \
     minio/minio server /data --console-address ":9001"
   ```

2. Set environment variables:
   ```bash
   export MINDTRACE_MINIO__MINIO_ENDPOINT=localhost:9000
   export MINDTRACE_MINIO__MINIO_ACCESS_KEY=minioadmin
   export MINDTRACE_MINIO__MINIO_SECRET_KEY=minioadmin
   export MINIO_SECURE=0
   ```

### For GCP Backend Tests
1. Set up Google Cloud credentials:
   ```bash
   # Option 1: Use application default credentials
   gcloud auth application-default login
   
   # Option 2: Set service account key
   export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account-key.json
   ```

2. Configure GCP settings (optional - defaults are in config.ini):
   ```bash
   export GCP_PROJECT_ID=your-project-id
   export GOOGLE_APPLICATION_CREDENTIALS=/path/to/credentials.json
   ```

   **Note**: Tests will use values from `config.ini` as defaults, with environment variables taking precedence.

## Running Tests

### Run All Integration Tests
```bash
cd tests/integration
pytest
```

### Run Specific Backend Tests
```bash
# Local backend only
pytest -m "not integration"

# MinIO backend only
pytest -m "minio"

# GCP backend only
pytest -m "gcp"

# All cloud backends
pytest -m "integration"
```

### Run Specific Test Files
```bash
# GCS storage tests
pytest mindtrace/storage/test_gcs_integration.py

# GCP registry backend tests
pytest mindtrace/registry/backend/test_gcp_registry_backend_integration.py

# All backend comparison tests
pytest mindtrace/registry/core/test_all_supported_backends_gcp.py
```

### Run with Verbose Output
```bash
pytest -v --tb=long
```

## Test Categories

### Storage Tests (`mindtrace/storage/`)
- **GCS Integration**: Tests for Google Cloud Storage handler
  - File upload/download operations
  - Metadata handling
  - Presigned URL generation
  - Concurrent operations
  - Error handling

### Registry Backend Tests (`mindtrace/registry/backend/`)
- **Local Backend**: Filesystem-based storage
- **MinIO Backend**: S3-compatible distributed storage
- **GCP Backend**: Google Cloud Storage distributed storage

Each backend test suite includes:
- Basic CRUD operations (push, pull, delete)
- Metadata management
- Object discovery (list objects, versions)
- Distributed locking
- Materializer registration
- Error handling
- Concurrent operations

### Registry Core Tests (`mindtrace/registry/core/`)
- **Multi-Backend Comparison**: Tests that run against all backends
- **Thread Safety**: Concurrent access testing
- **Distributed Concurrency**: Cross-backend locking tests

## Test Fixtures

### Common Fixtures
- `temp_dir`: Temporary directory for test files
- `sample_object_dir`: Directory with test files
- `sample_metadata`: Sample metadata for testing

### Backend-Specific Fixtures
- `gcs_client`: Google Cloud Storage client
- `test_bucket`: Temporary GCS bucket
- `backend`: Backend instance
- `registry`: Registry instance with backend

## Configuration

### Default Configuration
The tests use configuration from `mindtrace/core/mindtrace/core/config/config.ini` with the following GCP settings:

```ini
[MINDTRACE_GCP]
GCP_REGISTRY_URI = ${MINDTRACE_DIR_PATHS:ROOT}/gcp-registry
GCP_PROJECT_ID = mindtrace-test
GCP_BUCKET_NAME = mindtrace-registry
GCP_CREDENTIALS_PATH = 
GCP_LOCATION = US
GCP_STORAGE_CLASS = STANDARD
```

### Environment Variables
Environment variables override config.ini defaults:

#### GCP Tests
- `GCP_PROJECT_ID`: Google Cloud project ID (default: mindtrace-test)
- `GOOGLE_APPLICATION_CREDENTIALS`: Path to service account key (optional)

#### MinIO Tests
- `MINDTRACE_MINIO__MINIO_ENDPOINT`: MinIO server endpoint
- `MINDTRACE_MINIO__MINIO_ACCESS_KEY`: MinIO access key
- `MINDTRACE_MINIO__MINIO_SECRET_KEY`: MinIO secret key
- `MINIO_SECURE`: Use HTTPS (0 or 1)

## Troubleshooting

### GCP Authentication Issues
```bash
# Check authentication
gcloud auth list

# Re-authenticate if needed
gcloud auth application-default login
```

### MinIO Connection Issues
```bash
# Check MinIO is running
curl http://localhost:9000/minio/health/live

# Check MinIO logs
docker logs minio
```

### Test Cleanup Issues
The tests automatically clean up resources, but if cleanup fails:
```bash
# Clean up GCS buckets manually
gsutil -m rm -r gs://mindtrace-test-*

# Clean up MinIO buckets manually
mc rm -r --force minio/mindtrace-test-*
```

## Performance Testing

### Concurrent Operations
The tests include concurrent operation testing to verify:
- Distributed locking works correctly
- No race conditions occur
- Performance under load

### Load Testing
For more intensive testing:
```bash
# Run with more workers
pytest -n auto

# Run specific performance tests
pytest -k "concurrent" -v
```

## Continuous Integration

These tests are designed to run in CI environments with:
- Docker for MinIO server
- Google Cloud credentials for GCP tests
- Proper cleanup after test completion

The tests are marked with appropriate pytest markers for selective execution in different environments.

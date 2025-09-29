# pypylon Docker Service

This directory contains Docker configuration for running pypylon SDK integration tests without requiring local pypylon installation.

## Overview

The pypylon service provides a hybrid testing approach:
- **Host-based tests**: Tests run on your local machine for fast iteration
- **Docker-based pypylon**: pypylon SDK runs in a container to provide consistent environment
- **Socket communication**: Tests communicate with the containerized pypylon via Unix sockets

## Benefits

- **No local pypylon installation required**
- **Fast test iteration** (no container rebuilds)
- **Consistent test environment** across developers
- **CI/CD ready** with guaranteed pypylon availability
- **Easy onboarding** for new team members
- **Complete Basler SDK** with full hardware support
- **Flexible testing** - works with or without physical cameras

## Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Host Tests    │    │  Unix Socket     │    │ pypylon Service │
│                 │◄──►│  Communication   │◄──►│   (Docker)      │
│ - Fast iteration│    │ - /tmp/pypylon/  │    │ - Real pypylon  │
│ - Local IDE     │    │ - Pickle protocol│    │ - SDK operations│
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

## Usage

### Option 1: Automatic with ds test (Recommended)

The pypylon service automatically starts with all other services when running integration tests:

```bash
# Run pypylon integration tests (service starts automatically)
ds test: tests/integration/.../test_basler_pypylon_integration.py

# Run all integration tests (pypylon service included)
ds test --integration
```

### Option 2: Manual Docker Compose

Start the pypylon service manually:

```bash
# Start all integration services (including pypylon)
cd tests
docker-compose up -d

# Verify services are running
docker-compose ps

# Run tests (they will automatically use the service)
ds test: tests/integration/mindtrace/hardware/cameras/backends/basler/

# Stop services when done
docker-compose down
```

### Option 3: Direct Testing

Test the service directly:

```bash
# Start services (including pypylon)
cd tests
docker-compose up -d

# Test service functionality with pytest
pytest tests/utils/pypylon/test_service.py -v

# Expected output:
# === pypylon Service Test ===
# Testing pypylon availability...
# pypylon is available
# Proxy created successfully using backend: service
# Import test passed
# Device enumeration successful: 0 devices found
# ...
# 🎉 All tests passed! pypylon service is working correctly.
```

## Service Details

### Docker Service Configuration

- **Image**: Built from `tests/docker/pypylon-runtime.Dockerfile`
- **Base**: `ubuntu:22.04` with official Basler Pylon SDK
- **Socket**: `/tmp/pypylon/service.sock` (mounted as volume)
- **Health Check**: Verifies both Pylon SDK and pypylon work
- **Auto-start**: Starts with all integration tests
- **Hardware Support**: Includes USB/GigE drivers and debugging tools

### Communication Protocol

The service uses a simple request/response protocol over Unix sockets:

```python
# Request format
{
    'operation': 'enumerate_devices',
    'args': [],
    'kwargs': {}
}

# Response format
{
    'success': True,
    'devices': [
        {
            'serial_number': '12345',
            'model_name': 'acA1920-40uc',
            'vendor_name': 'Basler',
            ...
        }
    ]
}
```

### Supported Operations

- `import_test`: Test pypylon imports
- `enumerate_devices`: List available cameras
- `enumerate_interfaces`: List available interfaces
- `get_factory`: Test factory access
- `create_converter`: Test image format converter
- `get_pixel_formats`: Get pixel format constants
- `get_grabbing_strategies`: Get grabbing strategy constants
- `test_exceptions`: Test exception types

## Test Integration

Tests automatically detect and use the pypylon service:

```python
from tests.utils.pypylon.client import get_pypylon_proxy, is_pypylon_available

# Skip if neither local pypylon nor service available
if not is_pypylon_available():
    pytest.skip("Neither local pypylon nor pypylon service is available.")

@pytest.fixture
def pypylon_proxy():
    """Fixture providing pypylon proxy (local or service-based)."""
    return get_pypylon_proxy()

def test_pypylon_functionality(pypylon_proxy):
    """Test works with either local pypylon or service."""
    # This automatically uses the best available backend
    result = pypylon_proxy.import_test()
    assert result['success'] is True
```

## Development Workflow

### For Developers WITHOUT pypylon

1. **Run tests directly**: `ds test: tests/integration/.../pypylon_integration.py`
2. **Services auto-start**: pypylon and other services start automatically
3. **Develop tests**: Edit test files normally (no rebuilds needed)  
4. **Auto-cleanup**: Services stop automatically when tests complete

### For Developers WITH pypylon

1. **Run tests directly**: `ds test: tests/integration/.../pypylon_integration.py`
2. **Tests use local pypylon**: Faster execution, no Docker overhead
3. **Optional service testing**: Start service to test both backends

## Troubleshooting

### Service Won't Start

```bash
# Check service logs
docker-compose --profile pypylon logs pypylon-runtime

# Common issues:
# - Port conflicts (check if socket directory is accessible)
# - Build failures (check Docker build logs)
# - Health check failures (pypylon installation issues)
```

### Tests Skip with "pypylon not available"

```bash
# Check service status
docker-compose ps

# Verify socket exists
ls -la /tmp/pypylon/

# Test service directly with pytest
pytest tests/utils/pypylon/test_service.py -v
```

### Performance Issues

```bash
# Check if using service vs local
python -c "from tests.utils.pypylon.client import get_pypylon_proxy; print(get_pypylon_proxy().get_backend_type())"

# Service backend is ~10-20ms slower per operation
# Local backend is fastest
# For CI/CD, service provides consistency over speed
```

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Hardware Integration Tests
on: [push, pull_request]

jobs:
  hardware-tests:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v3
    
    - name: Start integration services
      run: |
        cd tests
        docker-compose up -d
    
    - name: Wait for service
      run: sleep 10
    
    - name: Run integration tests
      run: ds test --integration
    
    - name: Stop services
      run: |
        cd tests
        docker-compose down
```

This ensures pypylon integration tests always run in CI/CD regardless of runner environment.

## Future Enhancements

- **Multi-version testing**: Test against multiple pypylon versions
- **Mock camera simulation**: Simulate camera responses in Docker
- **Performance benchmarking**: Compare local vs service performance
- **Load testing**: Test service under concurrent test execution 
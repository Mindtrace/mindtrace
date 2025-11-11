# Hardware Test Suite

Stress testing framework for hardware components with process isolation, timeout guards, and guaranteed cleanup.

## Overview

The Hardware Test Suite provides a generalized framework for stress testing hardware APIs through realistic usage scenarios:

- **Guaranteed Cleanup**: Cleanup operations always execute via finally blocks, even on test failure
- **Timeout Protection**: Operation-level and scenario-level timeout guards
- **Graceful Error Handling**: Catches API errors, timeouts, and hardware failures
- **Comprehensive Monitoring**: Detailed metrics, failure tracking, and performance analysis
- **Scenario-Based Testing**: Predefined test scenarios for common usage patterns
- **YAML Configuration**: Easy-to-edit test configurations without code changes

## Architecture

```
test_suite/
├── core/                           # Generic framework (reusable)
│   ├── scenario.py                # Base scenario class with cleanup operations
│   ├── runner.py                  # Test execution engine with finally blocks
│   ├── monitor.py                 # Metrics and monitoring
│   └── __init__.py               # Core exports
│
└── cameras/                        # Camera-specific implementation
    ├── scenarios.py               # Predefined camera test scenarios
    ├── runner.py                  # Camera API endpoint mapping
    ├── config_loader.py           # YAML configuration loader
    ├── scenario_factory.py        # Scenario creation from YAML
    ├── run_test.py                # CLI interface
    ├── __init__.py                # Camera module exports
    └── config/                     # YAML test configurations
        ├── smoke_test.yaml
        ├── capture_stress.yaml
        ├── multi_camera.yaml
        ├── stream_stress.yaml
        ├── chaos_test.yaml
        └── soak_test.yaml
```

## Camera Test Scenarios

### Smoke Test
Quick validation of basic camera functionality.

**Operations**: Discover → Open → Configure → Capture → Close

**Duration**: ~3 seconds | **Expected Success**: 100%

### Capture Stress Test
High-frequency capture stress testing.

**Operations**: Discover → Open → Configure → 100 rapid captures → Close

**Duration**: ~3 seconds | **Expected Success**: 95%

### Multi-Camera Test
Concurrent camera operations with batch processing.

**Operations**: Discover → Open 4 cameras → Batch configure → 50 batch captures → Close all

**Duration**: ~15 seconds | **Expected Success**: 90%

### Stream Stress Test
Streaming stability and resource cleanup validation.

**Operations**: Discover → Open → Configure → 10 stream cycles (5s each) → Close

**Duration**: ~52 seconds | **Expected Success**: 90%

### Chaos Test
Edge case discovery through aggressive operations.

**Operations**: Rapid configuration changes, concurrent access, open/close cycles, mixed-state batch operations

**Duration**: ~4 seconds | **Expected Success**: 70% (deliberately aggressive)

### Soak Test
Long-duration stability testing for resource leak detection.

**Operations**: Discover → Open → Configure → 5000 captures → Close

**Duration**: ~8 hours | **Expected Success**: 85%

## Usage

### CLI Interface (Recommended)

The test suite is integrated into the main hardware CLI for streamlined execution:

```bash
# List available test configurations
uv run python -m mindtrace.hardware.cli camera test --list

# Run smoke test (basic functionality validation)
uv run python -m mindtrace.hardware.cli camera test --config smoke_test

# Run capture stress test (high-frequency capture)
uv run python -m mindtrace.hardware.cli camera test --config capture_stress

# Run multi-camera test with verbose output
uv run python -m mindtrace.hardware.cli camera test --config multi_camera -v

# Run long-duration soak test
uv run python -m mindtrace.hardware.cli camera test --config soak_test
```

**CLI Features:**
- Automatic Camera API availability check
- Interactive API startup if not running
- Formatted test results with ClickLogger styling
- Proper exit codes (0=pass, 1=config error, 2=fail)
- Verbose mode for detailed debugging

**Exit Codes:**
- `0` - Test passed (success rate meets expected threshold)
- `1` - Configuration error or test not found
- `2` - Test failed (success rate below expected threshold)

### Programmatic Usage

```python
import asyncio
from mindtrace.hardware.test_suite.cameras import CameraTestRunner
from mindtrace.hardware.test_suite.cameras.scenario_factory import create_scenario_from_config
from mindtrace.hardware.test_suite.core.monitor import HardwareMonitor

async def run_test():
    scenario = create_scenario_from_config("smoke_test")

    async with CameraTestRunner(scenario.api_base_url) as runner:
        monitor = HardwareMonitor(scenario.name)
        result = await runner.execute_scenario(scenario, monitor)
        monitor.print_summary()

asyncio.run(run_test())
```

### Custom Scenarios

```python
from mindtrace.hardware.test_suite.core.scenario import HardwareScenario, Operation, OperationType

scenario = HardwareScenario(
    name="custom_test",
    description="Custom camera test",
    api_base_url="http://localhost:8002",
    operations=[
        Operation(
            action=OperationType.DISCOVER,
            payload={"backend": "Basler"},
            timeout=10.0,
            store_result="cameras"
        ),
        Operation(
            action=OperationType.OPEN,
            payload={"camera": "$cameras[0]"},  # Variable substitution
            timeout=15.0
        ),
        Operation(
            action=OperationType.CAPTURE,
            payload={"camera": "$cameras[0]"},
            timeout=5.0,
            repeat=10,
            delay=0.1
        ),
    ],
    cleanup_operations=[
        Operation(
            action=OperationType.CLOSE,
            payload={"camera": "$cameras[0]"},
            timeout=5.0
        ),
    ],
    total_timeout=120.0,
    expected_success_rate=0.95
)
```

## YAML Configuration Format

```yaml
name: smoke_test
description: Quick smoke test for basic camera operations

api:
  base_url: http://localhost:8002
  timeout: 30.0

hardware:
  backend: Basler
  camera_count: 1

test:
  capture_count: 5
  exposure_us: 2000
  max_concurrent_captures: 1

expectations:
  total_timeout: 60.0
  expected_success_rate: 1.0

tags:
  - smoke
  - quick
  - basler
```

## Guaranteed Cleanup

All scenarios have `cleanup_operations` that execute in a `finally` block, ensuring cameras are always closed properly.

**Normal execution:**
```
DISCOVER → OPEN → CONFIGURE → CAPTURE → [finally: CLOSE]
```

**Failure during test:**
```
DISCOVER → OPEN → CONFIGURE → CAPTURE fails → [finally: CLOSE still runs]
```

**Implementation details:**
- Cleanup operations execute in `finally` block
- Failures during cleanup are logged but don't raise exceptions
- Variable substitution works in cleanup operations
- Best-effort cleanup continues even if individual operations fail

## Variable Substitution

The test suite supports dynamic variable substitution:

- `$variable_name` - entire stored result
- `$variable_name[0]` - first element of list
- `$variable_name[key]` - dictionary key access
- `$variable_name[0:4]` - list slicing

**Example:**
```python
Operation(
    action=OperationType.DISCOVER,
    store_result="cameras"  # Stores: ["Basler:40498643", "Basler:40498644"]
),
Operation(
    action=OperationType.OPEN,
    payload={"camera": "$cameras[0]"}  # Resolves to: "Basler:40498643"
),
```

## Metrics and Monitoring

The test suite tracks comprehensive metrics:

**Operation Metrics:**
- Total operations
- Success/failure/timeout counts
- Success rate percentage
- Average/min/max operation time
- Operations per second

**Error Tracking:**
- Error types and counts
- Top errors ranking
- Device-specific failures

**Example output:**
```
======================================================================
Test Summary: capture_stress
======================================================================
Duration: 2.92s
Operations: 4 total
  Success: 4 (100.0%)
  Failed: 0
  Timeout: 0

Performance:
  Avg time: 0.730s
  Min time: 0.005s
  Max time: 1.656s
  Ops/sec: 1.37
======================================================================
```

## API Endpoints

Camera test suite interacts with these endpoints:

- `/cameras/discover` - Discover cameras
- `/cameras/backends` - Get available backends
- `/cameras/open` - Open camera
- `/cameras/close` - Close camera
- `/cameras/open/batch` - Open multiple cameras
- `/cameras/close/batch` - Close multiple cameras
- `/cameras/close/all` - Close all open cameras
- `/cameras/configure` - Configure camera
- `/cameras/configure/batch` - Batch configuration
- `/cameras/capture` - Capture image
- `/cameras/capture/batch` - Batch capture
- `/cameras/stream/start` - Start streaming
- `/cameras/stream/stop` - Stop streaming
- `/cameras/status` - Get camera status

## Extension for Other Hardware

The core framework is hardware-agnostic. To add sensors, PLCs, or other hardware:

1. Create directory: `test_suite/sensors/`
2. Implement hardware-specific runner with endpoint mapping:
   ```python
   class SensorTestRunner(HardwareTestRunner):
       def _get_default_endpoint(self, action: OperationType) -> str:
           endpoint_map = {
               OperationType.DISCOVER: "/sensors/discover",
               OperationType.READ: "/sensors/read",
               # ...
           }
           return endpoint_map.get(action, f"/sensors/{action.value}")
   ```
3. Define hardware-specific scenarios
4. Create YAML configuration files
5. Create CLI runner script

Example structure:
```
test_suite/
├── core/           # Shared framework (no changes needed)
├── cameras/        # Camera tests
├── sensors/        # Sensor tests
└── plc/            # PLC tests
```

## Dependencies

- `httpx` - async HTTP requests
- `pyyaml` - configuration loading
- Running hardware API service (default: http://localhost:8002)

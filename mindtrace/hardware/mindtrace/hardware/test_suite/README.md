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
- **Mindtrace Framework Integration**: All classes inherit from Mindtrace for unified logging and configuration

## Quick Start

```bash
# List available tests
mindtrace-hw camera test --list

# Run smoke test
mindtrace-hw camera test --config smoke_test

# Run with verbose output
mindtrace-hw camera test --config capture_stress -v
```

📚 **See also:** [CLI Documentation](../cli/README.md) for complete CLI reference

## Architecture

```
test_suite/
├── core/                           # Generic framework (reusable)
│   ├── models.py                  # Base scenario and operation data models
│   ├── runner.py                  # Test execution engine with Mindtrace integration
│   ├── monitor.py                 # Metrics and monitoring with Mindtrace logging
│   └── __init__.py               # Core exports
│
└── cameras/                        # Camera-specific implementation
    ├── loader.py                  # YAML configuration loader and scenario factory
    ├── validator.py               # Camera parameter validation
    ├── __init__.py                # Camera module exports
    ├── README.md                  # Camera test suite documentation
    └── config/                     # YAML test configurations
        ├── template.yaml          # Template with all parameters documented
        ├── smoke_test.yaml        # Quick validation
        ├── capture_stress.yaml    # High-frequency capture stress
        ├── multi_camera.yaml      # Concurrent multi-camera operations
        ├── stream_stress.yaml     # Streaming stability testing
        ├── chaos_test.yaml        # Edge case discovery
        └── soak_test.yaml         # Long-duration stability
```

### Key Components

**Core Framework (Hardware-Agnostic):**
- `HardwareTestRunner` - Async test execution with process isolation
- `HardwareMonitor` - Real-time metrics tracking and reporting
- `HardwareScenario` - Test scenario data model with operations
- `Operation` - Individual test operation with timeout and retry support

**Camera Implementation:**
- `ConfigLoader` - Loads and validates YAML test configurations
- `ParameterValidator` - Validates camera parameters against CameraSettings
- YAML configs - Declarative test definitions without code changes

All classes inherit from `Mindtrace` or `MindtraceABC` for:
- Automatic structured logging via `self.logger`
- Configuration management via `self.config`
- Context manager support
- Consistent error handling

## Hardware-Specific Documentation

### Camera Tests
📚 **[Camera Test Suite Documentation](cameras/README.md)**

Comprehensive guide covering:
- Available test scenarios and when to use them
- YAML configuration format and all parameters
- Creating custom camera tests
- Template reference with complete parameter documentation

### Future Hardware
- **Sensors**: `test_suite/sensors/` (planned)
- **PLCs**: `test_suite/plc/` (planned)

## Usage

### CLI Interface (Recommended)

The test suite is integrated into the main hardware CLI:

```bash
# List available test configurations
mindtrace-hw camera test --list

# Run smoke test (basic functionality validation)
mindtrace-hw camera test --config smoke_test

# Run capture stress test (high-frequency capture)
mindtrace-hw camera test --config capture_stress

# Run multi-camera test with verbose output
mindtrace-hw camera test --config multi_camera -v

# Custom API endpoint
mindtrace-hw camera test --config smoke_test --api-port 8003
```

**CLI Features:**
- Automatic Camera API availability check
- Interactive API startup if not running
- Rich-formatted test results with progress bars
- Proper exit codes (0=pass, 1=config error, 2=fail)
- Verbose mode for detailed debugging

**Exit Codes:**
- `0` - Test passed (success rate meets expected threshold)
- `1` - Configuration error or test not found
- `2` - Test failed (success rate below expected threshold)

📚 **See also:** [CLI Documentation](../cli/README.md#camera-test) for complete CLI reference

### Programmatic Usage

```python
import asyncio
from mindtrace.hardware.test_suite.cameras.loader import create_scenario_from_config
from mindtrace.hardware.test_suite.core.runner import HardwareTestRunner
from mindtrace.hardware.test_suite.core.monitor import HardwareMonitor

async def run_test():
    # Load scenario from YAML config
    scenario = create_scenario_from_config("smoke_test")

    # Execute with context manager for automatic cleanup
    async with HardwareTestRunner(api_base_url=scenario.api_base_url) as runner:
        monitor = HardwareMonitor(scenario.name)
        result = await runner.execute_scenario(scenario, monitor)

        # Print formatted summary
        monitor.print_summary()

        # Check results
        if result.success_rate >= scenario.expected_success_rate:
            print("✅ Test passed")
        else:
            print("❌ Test failed")

asyncio.run(run_test())
```

### Custom Scenarios

```python
from mindtrace.hardware.test_suite.core.models import HardwareScenario, Operation, OperationType

scenario = HardwareScenario(
    name="custom_test",
    description="Custom camera test",
    api_base_url="http://localhost:8003",
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

## Guaranteed Cleanup

All scenarios have `cleanup_operations` that execute in a `finally` block, ensuring hardware is always released properly.

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

**Example output:**
```
======================================================================
Test Summary: capture_stress
======================================================================
Duration: 2.92s
Operations: 4 total
  [✓] Success: 4 (100.0%)
  [✗] Failed: 0
  [~] Timeout: 0

Performance:
  Avg time: 0.730s
  Min time: 0.005s
  Max time: 1.656s
  Ops/sec: 1.37
======================================================================
```

## Extension for Other Hardware

The core framework is hardware-agnostic. To add sensors, PLCs, or other hardware:

1. **Create directory**: `test_suite/sensors/`
2. **Implement hardware-specific runner** with endpoint mapping:
   ```python
   from mindtrace.hardware.test_suite.core.runner import HardwareTestRunner
   from mindtrace.hardware.test_suite.core.models import OperationType

   class SensorTestRunner(HardwareTestRunner):
       def _get_default_endpoint(self, action: OperationType) -> str:
           endpoint_map = {
               OperationType.DISCOVER: "/sensors/discover",
               OperationType.READ: "/sensors/read",
               # ...
           }
           return endpoint_map.get(action, f"/sensors/{action.value}")
   ```
3. **Define hardware-specific scenarios** in YAML
4. **Create config loader** (can reuse camera loader pattern)
5. **Add CLI command** in `cli/commands/`

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
- `mindtrace.core` - Mindtrace framework for logging and configuration
- Running hardware API service (default: http://localhost:8003)

## License

This project is part of the Mindtrace hardware management system.

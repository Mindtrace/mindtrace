# Camera Test Suite

Comprehensive stress testing and validation framework for camera hardware with YAML-driven configuration.

## Overview

The Camera Test Suite provides realistic hardware testing through declarative YAML configurations. All test logic lives in YAML files—no Python code needed for new tests.

**Key Features:**
- **YAML-Driven**: Define complete test scenarios in configuration files
- **Parameter Validation**: Automatic validation against CameraSettings schema
- **Variable Substitution**: Dynamic payload construction with `$variable` syntax
- **Guaranteed Cleanup**: Camera resources always released via finally blocks
- **Rich Reporting**: Detailed metrics, performance analysis, and failure tracking

## Quick Start

```bash
# List available tests
uv run python -m mindtrace.hardware.cli camera test --list

# Run smoke test (quick validation)
uv run python -m mindtrace.hardware.cli camera test --config smoke_test

# Run capture stress test
uv run python -m mindtrace.hardware.cli camera test --config capture_stress -v
```

📚 **See also:**
- [Test Suite Documentation](../README.md) for framework overview
- [CLI Documentation](../../cli/README.md#camera-test) for complete command reference

## Available Test Scenarios

### smoke_test.yaml
**Purpose**: Quick validation of basic camera functionality
**Duration**: ~10 seconds
**Operations**: Discover → Open → Configure → Single Capture → Close

**Use when:**
- Verifying camera API is running correctly
- Testing after configuration changes
- Quick hardware connectivity check
- CI/CD pipeline validation

### capture_stress.yaml
**Purpose**: High-frequency capture stress testing
**Duration**: ~2-5 minutes
**Operations**: 100 rapid capture iterations

**Use when:**
- Testing capture throughput limits
- Validating frame buffer handling
- Stress testing network bandwidth
- Performance benchmarking

### multi_camera.yaml
**Purpose**: Concurrent multi-camera operations
**Duration**: ~3-7 minutes
**Operations**: Parallel operations on 2+ cameras

**Use when:**
- Testing multi-camera setups
- Validating concurrent capture handling
- Bandwidth management verification
- Resource contention testing

### stream_stress.yaml
**Purpose**: Continuous streaming stability
**Duration**: ~5-10 minutes
**Operations**: Long-duration continuous capture

**Use when:**
- Testing sustained streaming workloads
- Memory leak detection
- Long-term stability validation
- Thermal stability testing

### chaos_test.yaml
**Purpose**: Edge case discovery and resilience testing
**Duration**: ~10-15 minutes
**Operations**: Random parameter changes, edge cases

**Use when:**
- Finding unexpected failure modes
- Validating error handling
- Testing parameter boundaries
- Chaos engineering scenarios

### soak_test.yaml
**Purpose**: Extended duration stability testing
**Duration**: 1+ hours
**Operations**: Repeated capture cycles over long period

**Use when:**
- Production readiness validation
- Long-term reliability testing
- Memory leak detection
- Thermal stability validation

## YAML Configuration Format

### Complete Structure

```yaml
# Test identification
name: my_camera_test
description: |
  What this test does and why.

# API configuration
api:
  base_url: http://localhost:8003
  timeout: 30.0

# Hardware selection
hardware:
  backend: Basler  # Basler, OpenCV, or Mock
  camera_selection:
    strategy: index  # index, serial, first, or all
    value: 0

# Camera configuration (see Parameter Reference below)
camera_config:
  runtime: { ... }   # Runtime-configurable parameters
  startup: { ... }   # Startup-only parameters
  system: { ... }    # System-level parameters

# Test execution
test:
  capture_count: 10
  delay_between_operations: 0.1
  parallel_operations: false

# Expectations
expectations:
  total_timeout: 300.0
  timeout_per_operation: 10.0
  expected_success_rate: 0.95

# Tags for organization
tags:
  - stress
  - validation

# Test operations sequence
operations:
  - action: discover
    payload: { ... }
    timeout: 10.0
    store_result: cameras

  - action: open
    payload:
      camera: "$cameras[0]"  # Variable substitution
    timeout: 15.0

  # ... more operations

# Cleanup (always runs)
cleanup_operations:
  - action: close
    payload: { ... }
    timeout: 5.0
```

### Variable Substitution

Reference values from elsewhere in the config using `$path.to.value` syntax:

```yaml
# Store discovery results
- action: discover
  store_result: cameras

# Use stored results
- action: open
  payload:
    camera: "$cameras[0]"              # First camera

- action: configure
  payload:
    camera: "$cameras[0]"
    properties: "$camera_config.runtime"  # All runtime params

# Reference config values
- action: discover
  payload:
    backend: "$hardware.backend"       # Reference hardware.backend field
```

**Supported syntax:**
- `$variable` - entire value
- `$variable[0]` - array index
- `$variable[key]` - dictionary key
- `$path.to.nested.value` - nested access

## Parameter Reference

Camera parameters are organized into three categories aligned with `CameraSettings` from `mindtrace.hardware.core.config`:

### RUNTIME Parameters
**Changeable during operation** via `/cameras/configure` API

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `timeout_ms` | int | 5000 | Capture timeout in milliseconds (SDK-level) |
| `exposure_time` | float | 1000.0 | Exposure time in microseconds (100-50000) |
| `gain` | float | 1.0 | Camera gain/brightness (0.0-4.0) |
| `trigger_mode` | str | "continuous" | Trigger mode: "continuous" or "trigger" |
| `white_balance` | str | "auto" | White balance: "auto", "off", or "once" |
| `pixel_format` | str | "BGR8" | Pixel format (BGR8, RGB8, Mono8, YUV422) |
| `image_quality_enhancement` | bool | false | Enable CLAHE contrast enhancement |

**OpenCV Backend Specific:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `opencv_default_width` | int | 1280 | Frame width in pixels (640, 1280, 1920) |
| `opencv_default_height` | int | 720 | Frame height in pixels (480, 720, 1080) |
| `opencv_default_fps` | int | 30 | Frames per second (15, 30, 60) |
| `opencv_default_exposure` | float | -1.0 | Exposure control (-1 = auto, 0-1 = manual) |

### STARTUP Parameters
**Require camera reinitialization** to change (not configurable at runtime)

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `buffer_count` | int | 25 | Number of frame buffers (10-50) |
| `basler_multicast_enabled` | bool | false | Enable multicast mode (Basler only) |
| `basler_multicast_group` | str | "239.192.1.1" | Multicast group IP address |
| `basler_multicast_port` | int | 3956 | Multicast port number |
| `basler_target_ips` | list | [] | Target IPs for camera discovery |

### SYSTEM Parameters
**Manager-level settings** affecting overall camera system behavior

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `retrieve_retry_count` | int | 3 | Retry attempts for failed captures (0-5) |
| `max_concurrent_captures` | int | 2 | Max simultaneous captures (bandwidth mgmt) |
| `max_camera_index` | int | 1 | Max camera index to scan (OpenCV only) |
| `mock_camera_count` | int | 10 | Number of mock cameras (Mock backend) |
| `enhancement_gamma` | float | 2.2 | Gamma correction for enhancement (1.0-3.0) |
| `enhancement_contrast` | float | 1.2 | Contrast enhancement factor (0.5-2.0) |

**OpenCV Validation Ranges:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `opencv_exposure_range_min` | float | -13.0 | Minimum exposure value |
| `opencv_exposure_range_max` | float | -1.0 | Maximum exposure value |
| `opencv_width_range_min` | int | 160 | Minimum frame width |
| `opencv_width_range_max` | int | 1920 | Maximum frame width |
| `opencv_height_range_min` | int | 120 | Minimum frame height |
| `opencv_height_range_max` | int | 1080 | Maximum frame height |

📚 **Complete reference:** See [template.yaml](config/template.yaml) for full documentation with examples and ranges.

## Creating Custom Tests

### 1. Copy the Template

```bash
cp config/template.yaml config/my_custom_test.yaml
```

### 2. Update Test Identification

```yaml
name: my_custom_test
description: |
  Custom test for specific scenario.

  Purpose: Test high-gain low-light capture
  Scope: Single camera, 50 captures
  Duration: ~30 seconds

tags:
  - custom
  - low-light
```

### 3. Configure Camera Parameters

```yaml
camera_config:
  runtime:
    exposure_time: 10000.0    # 10ms for low light
    gain: 3.0                 # High gain
    pixel_format: "Mono8"     # Grayscale
    timeout_ms: 8000          # Longer timeout

  system:
    retrieve_retry_count: 5   # More retries for difficult conditions
```

### 4. Define Operations Sequence

```yaml
operations:
  - action: discover
    payload:
      backend: "Basler"
    timeout: 10.0
    store_result: cameras

  - action: open
    payload:
      camera: "$cameras[0]"
      test_connection: true
    timeout: 15.0

  - action: configure
    payload:
      camera: "$cameras[0]"
      properties: "$camera_config.runtime"
    timeout: 5.0

  - action: capture
    payload:
      camera: "$cameras[0]"
    timeout: 10.0
    repeat: 50              # 50 capture iterations
    delay: 0.2              # 200ms between captures

cleanup_operations:
  - action: close
    payload:
      camera: "$cameras[0]"
    timeout: 5.0
```

### 5. Set Expectations

```yaml
expectations:
  total_timeout: 180.0           # 3 minutes max
  timeout_per_operation: 15.0    # Per-operation timeout
  expected_success_rate: 0.90    # 90% success acceptable
```

### 6. Run Your Test

```bash
uv run python -m mindtrace.hardware.cli camera test --config my_custom_test
```

## Available Actions

### discover
**Purpose**: Find available cameras for a backend

```yaml
- action: discover
  payload:
    backend: "Basler"  # Basler, OpenCV, or Mock
  timeout: 10.0
  store_result: cameras  # Store result for later use
```

**Returns**: List of camera identifiers (e.g., `["Basler:40498643", "Basler:40498644"]`)

### open
**Purpose**: Open camera connection

```yaml
- action: open
  payload:
    camera: "$cameras[0]"      # Camera identifier
    test_connection: true      # Verify connection works
  timeout: 15.0
```

### configure
**Purpose**: Update camera settings (runtime parameters only)

```yaml
- action: configure
  payload:
    camera: "$cameras[0]"
    properties:                    # Any runtime parameters
      exposure_time: 2000.0
      gain: 1.5
      pixel_format: "BGR8"
  timeout: 5.0
```

### capture
**Purpose**: Capture image/frame

```yaml
- action: capture
  payload:
    camera: "$cameras[0]"
  timeout: 10.0
  repeat: 10        # Optional: repeat N times
  delay: 0.1        # Optional: delay between repeats (seconds)
```

### close
**Purpose**: Close camera connection

```yaml
- action: close
  payload:
    camera: "$cameras[0]"
  timeout: 5.0
```

## Test Execution Parameters

Control test behavior (separate from camera configuration):

```yaml
test:
  capture_count: 10               # Number of capture iterations
  delay_between_operations: 0.1   # Delay between ops (seconds)
  parallel_operations: false      # Run operations in parallel
```

## Hardware Selection Strategies

### index - Select by camera index
```yaml
hardware:
  backend: Basler
  camera_selection:
    strategy: index
    value: 0  # First camera (0-indexed)
```

### serial - Select by serial number
```yaml
hardware:
  backend: Basler
  camera_selection:
    strategy: serial
    value: "40498643"  # Specific camera serial
```

### first - Use first discovered camera
```yaml
hardware:
  backend: Basler
  camera_selection:
    strategy: first
    # No value needed
```

### all - Test all discovered cameras
```yaml
hardware:
  backend: Basler
  camera_selection:
    strategy: all
    # No value needed - operations run on all cameras
```

## Examples

### Example 1: Quick Smoke Test

```yaml
name: quick_check
description: Minimal test for API validation

api:
  base_url: http://localhost:8003
  timeout: 30.0

hardware:
  backend: Mock  # Use mock for fast testing
  camera_selection:
    strategy: first

camera_config:
  runtime:
    timeout_ms: 3000
    pixel_format: "BGR8"

expectations:
  total_timeout: 60.0
  expected_success_rate: 1.0  # 100% success expected

operations:
  - action: discover
    payload:
      backend: "$hardware.backend"
    timeout: 5.0
    store_result: cameras

  - action: open
    payload:
      camera: "$cameras[0]"
    timeout: 10.0

  - action: capture
    payload:
      camera: "$cameras[0]"
    timeout: 5.0

cleanup_operations:
  - action: close
    payload:
      camera: "$cameras[0]"
    timeout: 5.0
```

### Example 2: Performance Benchmark

```yaml
name: performance_benchmark
description: Measure maximum capture throughput

hardware:
  backend: Basler
  camera_selection:
    strategy: index
    value: 0

camera_config:
  runtime:
    timeout_ms: 1000       # Fast timeout
    exposure_time: 500.0   # Short exposure
    pixel_format: "Mono8"  # Fastest format

  system:
    max_concurrent_captures: 1  # Single-threaded for pure measurement

test:
  capture_count: 200
  delay_between_operations: 0.0  # No artificial delay

expectations:
  total_timeout: 120.0
  expected_success_rate: 0.98

operations:
  - action: discover
    payload:
      backend: "$hardware.backend"
    timeout: 10.0
    store_result: cameras

  - action: open
    payload:
      camera: "$cameras[0]"
    timeout: 15.0

  - action: configure
    payload:
      camera: "$cameras[0]"
      properties: "$camera_config.runtime"
    timeout: 5.0

  - action: capture
    payload:
      camera: "$cameras[0]"
    timeout: 2.0
    repeat: "$test.capture_count"
    delay: "$test.delay_between_operations"

cleanup_operations:
  - action: close
    payload:
      camera: "$cameras[0]"
    timeout: 5.0
```

## Validation

All camera parameters are automatically validated against the `CameraSettings` schema:

- **Type checking**: Ensures correct data types
- **Range validation**: Values within acceptable ranges
- **Required fields**: Catches missing required parameters
- **Extra fields**: Warns about unknown parameters

Validation errors are caught before test execution:

```
❌ Configuration Error: Invalid camera parameter 'exposure_time'
   Expected: float between 100.0 and 50000.0
   Got: 100000.0
```

## Programmatic Usage

```python
from mindtrace.hardware.test_suite.cameras.loader import create_scenario_from_config
from mindtrace.hardware.test_suite.core.runner import HardwareTestRunner
from mindtrace.hardware.test_suite.core.monitor import HardwareMonitor

async def run_custom_test():
    # Load scenario from YAML
    scenario = create_scenario_from_config("my_custom_test")

    # Execute with automatic cleanup
    async with HardwareTestRunner(api_base_url=scenario.api_base_url) as runner:
        monitor = HardwareMonitor(scenario.name)
        result = await runner.execute_scenario(scenario, monitor)

        # Print results
        monitor.print_summary()

        # Check success
        if result.success_rate >= scenario.expected_success_rate:
            print("✅ Test passed")
        else:
            print("❌ Test failed")
```

## Troubleshooting

### Camera Not Found

```
❌ No cameras discovered for backend: Basler
```

**Solutions:**
- Verify Camera API is running: `curl http://localhost:8003/health`
- Check camera physical connection
- Try `backend: Mock` for testing without hardware
- Verify `basler_target_ips` if using specific IPs

### Timeout Errors

```
❌ Operation timeout: capture exceeded 5.0 seconds
```

**Solutions:**
- Increase `timeout_ms` in runtime config
- Increase `timeout_per_operation` in expectations
- Check network bandwidth (for IP cameras)
- Reduce `exposure_time` for faster captures

### Low Success Rate

```
⚠️ Success rate 0.85 below expected 0.95
```

**Solutions:**
- Review error details in test output
- Increase `retrieve_retry_count` for resilience
- Adjust `max_concurrent_captures` to reduce contention
- Check hardware stability and thermal conditions
- Verify network bandwidth for multi-camera setups

## Next Steps

- **Run existing tests**: Start with `smoke_test` to validate setup
- **Review template**: Study [template.yaml](config/template.yaml) for complete parameter reference
- **Create custom tests**: Copy template and customize for your scenarios
- **Explore CLI**: See [CLI Documentation](../../cli/README.md#camera-test) for advanced usage
- **Understand framework**: Read [Test Suite Overview](../README.md) for architecture details

## Related Documentation

- [Test Suite Framework](../README.md) - Core framework architecture and extension guide
- [CLI Reference](../../cli/README.md#camera-test) - Complete command-line interface documentation
- [Camera API](../../api/README.md) - Camera API endpoints and usage (if exists)
- [Configuration Reference](../../core/config/README.md) - CameraSettings schema details (if exists)

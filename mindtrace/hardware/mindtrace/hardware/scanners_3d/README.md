# Mindtrace 3D Scanner System

The `3D Scanner` module provides Mindtrace’s interface for structured-light scanning workflows, including async and sync scanner access, point-cloud generation, configuration management, and service-based deployment.

## Features

- **Async and sync scanner interfaces** with `AsyncScanner3D` and `Scanner3D`
- **Structured multi-component capture** including range, intensity, confidence, normals, and color
- **Point-cloud generation** through `PointCloudData`
- **Photoneo backend support** through `PhotoneoBackend`
- **Service-oriented deployment** with scanner services and connection managers
- **Backend setup tooling** through the Photoneo setup CLI entry point

## Quick Start

```python
import asyncio

from mindtrace.hardware.scanners_3d import AsyncScanner3D


async def main():
    async with await AsyncScanner3D.open() as scanner:
        result = await scanner.capture()
        print(result.range_shape)

        point_cloud = await scanner.capture_point_cloud()
        print(point_cloud.num_points)
        point_cloud.save_ply("output.ply")


asyncio.run(main())
```

This module is built around a simple progression:

- open a scanner
- capture structured scan data
- optionally generate a point cloud
- configure the scanner as needed
- expose the scanner through a service when you want remote access

## Core Interfaces

The main exports are:

- `AsyncScanner3D`
- `Scanner3D`
- `ScanResult`
- `ScanComponent`
- `CoordinateMap`
- `PointCloudData`
- `PhotoneoBackend`

### Async interface

Use `AsyncScanner3D` for long-running applications, orchestration, and service-style workflows.

```python
import asyncio

from mindtrace.hardware.scanners_3d import AsyncScanner3D


async def capture_scan():
    async with await AsyncScanner3D.open("Photoneo:ABC123") as scanner:
        result = await scanner.capture(
            enable_range=True,
            enable_intensity=True,
            enable_confidence=True,
            enable_normal=True,
            enable_color=True,
            timeout_ms=10000,
        )

        print(result.range_shape)
        print(result.intensity_shape)


asyncio.run(capture_scan())
```

### Sync interface

Use `Scanner3D` when you want a more script-like synchronous workflow.

```python
from mindtrace.hardware.scanners_3d import Scanner3D


with Scanner3D() as scanner:
    result = scanner.capture()
    point_cloud = scanner.capture_point_cloud()
    point_cloud.save_ply("scan.ply")
```

## Capture Workflows

### Multi-component capture

A scan can include multiple components depending on backend support and configuration.

```python
result = await scanner.capture(
    enable_range=True,
    enable_intensity=True,
    enable_confidence=True,
    enable_normal=True,
    enable_color=True,
)
```

Typical components include:

- range / depth
- intensity
- confidence
- surface normals
- color

### Point clouds

```python
point_cloud = await scanner.capture_point_cloud(
    include_colors=True,
    include_confidence=True,
    downsample_factor=2,
)

print(point_cloud.num_points)
point_cloud.save_ply("scan.ply")
```

## Discovery and Backends

The scanner package currently centers around `PhotoneoBackend`.

Example discovery flow:

```python
from mindtrace.hardware.scanners_3d.backends.photoneo import PhotoneoBackend


serials = PhotoneoBackend.discover()
print(serials)
```

Open by explicit name when needed:

```python
scanner = await AsyncScanner3D.open("Photoneo:ABC123")
```

## Configuration

Use the scanner configuration APIs when you need to inspect or adjust runtime parameters.

### Bulk configuration

```python
from mindtrace.hardware.scanners_3d.core.models import CodingQuality, OperationMode, ScannerConfiguration


config = await scanner.get_configuration()
print(config.exposure_time)

new_config = ScannerConfiguration(
    operation_mode=OperationMode.SCANNER,
    coding_quality=CodingQuality.HIGH,
    exposure_time=15.0,
    led_power=2048,
)
await scanner.set_configuration(new_config)
```

### Individual settings

```python
await scanner.set_exposure_time(10.24)
exposure = await scanner.get_exposure_time()
print(exposure)

await scanner.set_trigger_mode("Software")
mode = await scanner.get_trigger_mode()
print(mode)
```

### Capabilities

```python
caps = await scanner.get_capabilities()
print(caps.model)
print(caps.coding_qualities)
print(caps.exposure_range)
```

## Services and Remote Access

The scanner subsystem can be exposed through the Mindtrace hardware services layer.

Top-level service exports in the hardware package include:

- `Scanner3DService`
- `Scanner3DConnectionManager`

### Launch a scanner service

```python
from mindtrace.hardware.services import Scanner3DService


cm = Scanner3DService.launch(port=8005, wait_for_launch=True)
print(cm.status())
```

### Connect to an existing scanner service

```python
from mindtrace.hardware.services import Scanner3DConnectionManager


client = Scanner3DConnectionManager("http://localhost:8005")
```

### CLI workflow

```bash
$ mindtrace-hw scanner start --open-docs
$ mindtrace-hw scanner status
$ curl http://localhost:8005/status
```

When the service is running, its generated docs are typically available at:

- `http://localhost:8005/docs`

## SDK Setup

The Photoneo workflow may require additional backend setup beyond the Python package itself.

The package exposes a setup entry point for that workflow:

```bash
$ mindtrace-scanner-photoneo --help
```

Examples:

```bash
$ mindtrace-scanner-photoneo install -v
$ mindtrace-scanner-photoneo verify -v
$ mindtrace-scanner-photoneo discover
```

## Installation

Base package install:

```bash
$ uv add mindtrace-hardware
```

Or with pip and scanner support:

```bash
$ pip install 'mindtrace-hardware[scanners-photoneo]'
```

If you are working from the full Mindtrace repo:

```bash
$ git clone https://github.com/Mindtrace/mindtrace.git && cd mindtrace
$ uv sync --dev --all-extras
```

## Examples

Related docs in this package:

- [Top-level hardware module README](../../../../README.md)
- [Hardware CLI documentation](../cli/README.md)

## Testing

If you are working in the full Mindtrace repo, run tests for the hardware module:

```bash
$ git clone https://github.com/Mindtrace/mindtrace.git && cd mindtrace
$ uv sync --dev --all-extras
$ ds test: hardware
$ ds test: --unit hardware
```

When possible, prefer development and CI workflows that do not require live hardware unless you are specifically validating device integration.

## Practical Notes and Caveats

- Scanner functionality depends heavily on backend support and the installed SDK/toolchain.
- `AsyncScanner3D` is usually the best choice for integrations and services; `Scanner3D` is convenient for simpler scripts.
- Point-cloud workflows can produce large outputs, so file writing and memory usage matter in real deployments.
- Service deployment is useful when scanners should be accessed remotely or through agent/tool workflows.
- This README focuses on the practical scanner workflow; deeper backend-specific details belong in the implementation and code docs.

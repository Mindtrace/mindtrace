# Mindtrace Hardware CLI

The `Hardware CLI` provides command-line management for Mindtrace hardware services, including service startup, shutdown, status checks, logs, and common operational workflows.

## Features

- **Service lifecycle management** for camera, stereo, scanner, and PLC services
- **Health and status inspection** across all managed services
- **Process tracking** with graceful shutdown behavior
- **Convenient docs access** through `--open-docs` for supported services
- **Configuration overrides** via CLI flags and environment variables
- **A single operational entry point** through `mindtrace-hw`

## Quick Start

```bash
$ mindtrace-hw camera start --open-docs
$ mindtrace-hw camera status
$ mindtrace-hw stop
```

The CLI is primarily for operating hardware services in practice: starting them, checking whether they are healthy, opening their docs, and stopping them cleanly.

## Service Commands

The CLI exposes service-oriented subcommands for the hardware domains it currently manages.

### Camera service

```bash
$ mindtrace-hw camera start
$ mindtrace-hw camera start --open-docs
$ mindtrace-hw camera status
$ mindtrace-hw camera logs
$ mindtrace-hw camera stop
```

### Stereo camera service

```bash
$ mindtrace-hw stereo start
$ mindtrace-hw stereo start --open-docs
$ mindtrace-hw stereo status
$ mindtrace-hw stereo logs
$ mindtrace-hw stereo stop
```

### 3D scanner service

```bash
$ mindtrace-hw scanner start
$ mindtrace-hw scanner start --open-docs
$ mindtrace-hw scanner status
$ mindtrace-hw scanner logs
$ mindtrace-hw scanner stop
```

### PLC service

```bash
$ mindtrace-hw plc start
$ mindtrace-hw plc status
$ mindtrace-hw plc logs
$ mindtrace-hw plc stop
```

## Global Commands

Use the top-level commands when you want to inspect or stop the full set of managed services.

```bash
$ mindtrace-hw status
$ mindtrace-hw stop
$ mindtrace-hw logs all
```

You can also inspect logs for a specific service group:

```bash
$ mindtrace-hw logs camera
$ mindtrace-hw logs scanner
$ mindtrace-hw logs stereo
$ mindtrace-hw logs plc
```

## Common Workflows

### Start a service and open its docs

```bash
$ mindtrace-hw scanner start --open-docs
$ mindtrace-hw scanner status
```

### Start on a custom host and port

```bash
$ mindtrace-hw camera start --api-host 0.0.0.0 --api-port 8080
$ mindtrace-hw camera status
```

### Start camera service with mock devices

```bash
$ mindtrace-hw camera start --include-mocks
$ mindtrace-hw camera status
```

### Inspect everything, then stop everything

```bash
$ mindtrace-hw status
$ mindtrace-hw stop
```

## What the CLI manages

Operationally, the CLI is responsible for things like:

- checking whether a service is already running
- validating port availability before startup
- tracking service processes
- reporting status, uptime, and basic health information
- stopping services gracefully before escalating if needed

That makes it the practical control surface for service-based hardware deployments.

## Configuration

CLI options can override service host and port at launch time.

Examples:

```bash
$ mindtrace-hw camera start --api-host 192.168.1.100 --api-port 8080
$ mindtrace-hw stereo start --api-host 0.0.0.0 --api-port 8004
$ mindtrace-hw scanner start --api-host 0.0.0.0 --api-port 8005
$ mindtrace-hw plc start --api-host 0.0.0.0 --api-port 8003
```

The CLI also supports environment-driven configuration. In practice, command-line flags take precedence over environment defaults.

## Installation

If you are working from the full Mindtrace repo:

```bash
$ git clone https://github.com/Mindtrace/mindtrace.git && cd mindtrace
$ uv sync --dev --all-extras
```

If you want the CLI entry point available locally from the hardware package:

```bash
$ uv pip install -e mindtrace/hardware/
$ mindtrace-hw --help
```

## Troubleshooting

### Port already in use

```bash
$ mindtrace-hw camera status
$ mindtrace-hw camera start --api-port 8003
```

### Service won’t start cleanly

```bash
$ mindtrace-hw camera status
$ mindtrace-hw camera stop
$ mindtrace-hw camera start
```

### Need log guidance

```bash
$ mindtrace-hw logs camera
$ mindtrace-hw logs all
```

## Examples

Related docs in this package:

- [Top-level hardware module README](../../../../README.md)
- [3D scanner subsystem documentation](../scanners_3d/README.md)

## Testing

If you are working in the full Mindtrace repo, run tests for the hardware module:

```bash
$ git clone https://github.com/Mindtrace/mindtrace.git && cd mindtrace
$ uv sync --dev --all-extras
$ ds test: hardware
$ ds test: --unit hardware
```

## Practical Notes and Caveats

- The CLI currently manages camera, stereo, scanner, and PLC services directly.
- Some capabilities depend on the underlying hardware services and installed backend extras.
- `--open-docs` is useful when you want to verify service startup quickly through `/docs`.
- Camera workflows may support mock devices for development; not every hardware domain has the same mock story.
- The CLI is best treated as an operational tool for service-based workflows rather than a replacement for the underlying Python APIs.

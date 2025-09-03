[![PyPI version](https://img.shields.io/pypi/v/mindtrace)](https://pypi.org/project/mindtrace/)
[![License](https://img.shields.io/pypi/l/mindtrace)](https://github.com/mindtrace/mindtrace/blob/main/LICENSE)
[![Downloads](https://static.pepy.tech/badge/mindtrace)](https://pepy.tech/projects/mindtrace)

# Mindtrace Module Dependency Structure

Mindtrace is organized into a layered workspace to support ML components as Python modules with clearly defined boundaries and dependencies.

---

## 📐 Layered Architecture

We use a level-based system for organizing modules based on dependency direction and build order.

### **Level 1: Core**
- `core`: Foundational utilities and base classes used across all other modules.

### **Level 2: Core Consumers**
- `jobs`: Job execution and backend interfaces.
- `registry`: Artifact and metadata management.
- `database`: Redis, Mongo, and DB access layers.
- `services`: Service base classes, authentication, and gateways.
- `ui`: Optional UI libraries and components.

### **Level 3: Infrastructure Modules**
- `hardware`: Interfaces for cameras, PLCs, scanners, etc.
- `cluster`: Runtime cluster management, nodes, and workers.
- `datalake`: Dataset interfaces for HuggingFace and Mindtrace datasets.
- `models`: Core model definitions and leaderboard utilities.

### **Level 4: Automation**
- `automation`: Integration of pipelines and orchestration using level 2–3 modules.

### **Level 5: Applications**
- `apps`: End-user applications composed of all previous levels.
  - E.g., Demo pipelines

---

## 🔄 Dependency Flow

Each layer only depends on modules in lower levels.

| Module     | Depends On                                           |
|------------|------------------------------------------------------|
| `core`     | –                                                    |
| `jobs`     | `core`, `services`                                   |
| `registry` | `core`                                               |
| `database` | `core`                                               |
| `services` | `core`                                               |
| `ui`       | `core`                                               |
| `cluster`  | `jobs`, `registry`, `database`, `services`           |
| `datalake` | `registry`, `database`, `services`                   |
| `models`   | `registry`, `services`                               |
| `hardware` | `core`                                               | 
| `automation` | `jobs`, `registry`, `database`, `services`, `datalake`, `models`, `cluster` |
| `apps`     | Everything                                           |

---


## 🛠️ Build

Building wheels and source distributions, from the root of the repo:  
```bash
uv build --all-packages
ls dist/
```
For building only wheels:  
```bash
uv build --all-packages --wheel
ls dist/
```
They may then be installed in a new venv (the entire `mindtrace` package or any submodule `mindtrace-core`) via:  
```bash
uv pip install mindtrace --find-links /path/to/dist
# or
uv pip install /path/to/dist/mindtrace.whl
```
Note: You may need to use `uv pip install --force-reinstall` in case you encounter `ModuleNotFoundError`.  
Checking the installation:  
```bash
uv run python -c "from mindtrace.core import Mindtrace; print('OK')"
```


## 🛠️ Usage Examples

Installing the full Mindtrace package:
```bash
uv add mindtrace
```
Installing a minimal dependency chain (e.g., for Datalake development):
```bash
uv add mindtrace-datalake
```
Python Imports
```python
from mindtrace import core, registry, database, services
```



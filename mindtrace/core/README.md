# Mindtrace Core

The foundational module of the Mindtrace ML framework, providing essential utilities, base classes, and core abstractions used across all other Mindtrace modules.

## Purpose

`mindtrace-core` serves as the foundation layer (Level 1) in the Mindtrace architecture, offering:

- **Base Classes**: Abstract base classes and metaclasses for consistent architecture
- **Configuration Management**: Centralized configuration handling
- **Event System**: Observable patterns and event bus for inter-component communication
- **Utilities**: Common utility functions for dynamic imports, type checking, and more
- **Logging**: Structured logging capabilities

## Installation

```bash
# Install as standalone package
uv add mindtrace-core

# Or install as part of full Mindtrace
uv add mindtrace
```

## Architecture

The core module is organized into several submodules:

### Base Classes (`base/`)
- `MindtraceABC`: Abstract base class for all Mindtrace components
- `MindtraceMeta`: Metaclass providing common functionality
- `Mindtrace`: Main base class with core functionality

### Configuration (`config/`)
- `Config`: Centralized configuration management system

### Observables (`observables/`)
- `EventBus`: Publish-subscribe event system
- `ObservableContext`: Context management with observation capabilities
- `ContextListener`: Event listening and handling

### Utilities (`utils/`)
- `checks`: Type checking and validation utilities
- `dynamic`: Dynamic class instantiation and import helpers

### Logging (`logging/`)
- Structured logging configuration and utilities

## API Reference

### Core Classes

#### `Mindtrace`
Base class for all Mindtrace components.

```python
class MyProcessor(Mindtrace):
    def __init__(self):
        super().__init__()
```

#### `Config`
Configuration management with validation and defaults.

```python
config = Config({
    "param1": "value1",
    "param2": 42
})
```

### Observables

The Observables module enables lightweight observability and reactivity for class objects, automatically turning selected properties into observable variables. This framework allows external components (listeners) to be notified whenever specific values change, without hard-coding the coupling between the source and observers.

There are three main classes included in the `observables` module:

---

### 1. `EventBus`

The `EventBus` is a lightweight internal publish-subscribe system for event dispatching. 

**API:**

Event buses expose three main methods, which may be used to `subscribe`/`unsubscribe` individual listeners and `emit` event messages.

```python
subscribe(handler: Callable, event_name: str) -> str
unsubscribe(handler_or_id: Union[str, Callable], event_name: str)
emit(event_name: str, **kwargs)
```

**Example Usage:**
To use an event bus, subscribe a handler to the bus with an associated event name. The handler will be called any time the event name is emitted. 

```python
from mindtrace.core import EventBus

bus = EventBus()    

def handler(**kwargs):
    print(kwargs)

bus.subscribe(handler, "event")
bus.emit("event", x="1", y="2")  # {'x': '1', 'y': '2'}

bus.unsubscribe(handler, "event")
bus.emit("event", x="1", y="2")  # No output
```

---

### 2. `ObservableContext`

The `ObservableContext` class decorator automatically turns specified properties into observable fields and wires up listener support.

The `ObservableContext` class supports two specific event types, with associated event names:

1. `context_updated(source: str, var: str, old: any, new: any)`: May be used when _any_ observed variable changes. The name of the variable will be given as the `var` argument, with associated old and new values.
2. `{var}_updated(source: str, old: any, new: any)`: May be used to listen to specific variables. Effectively a shorthand for:

**API:**

The `ObservableContext` decorator adds `subscribe` and `unsubscribe` methods onto a wrapped class, which may be used directly analogously to with the `EventBus`.

```python
subscribe(handler, event_name)
unsubscribe(handler_or_id, event_name)
```

**Example Usage:**

When subscribing a class-derived listener, define a `context_updated` method which will be notified anytime any observable variable is updated, or specific `{var}_updated` methods, which will be notified when the associated variable is updated.

```python
class MyListener:
    def context_updated(self, source, var, old, new):  # May be omitted, `{var}_updated` methods will be called automatically
        if var == "x":
            return self.x_updated(source, old, new)
        elif var == "y":
            return self.y_updated(source, old, new)
    def x_updated(...): ...
    def y_updated(...): ...
```

Listeners may subscribe to any class that has been decorated with the `ObservaleContext` decorator, listening to any of the listed `vars` in the decorator.

```python
from mindtrace.core import ObservableContext

@ObservableContext(vars=["x", "y"])
class MyContext:
    def __init__(self):
        self.x = 0
        self.y = 0

class MyListener:
    def x_changed(self, source, old, new):
        print(f"[{source}] x changed from {old} to {new}")

my_context = MyContext()
my_context.subscribe(MyListener())

my_context.x = 1  # [MyContext] x changed from 0 to 1
```

---

### 3. `ContextListener(Mindtrace)`

The `ContextListener` class is a helper class for defining observers that respond to context changes. This class is meant to provide two benefits: (1) deriving from the `Mindtrace` base class, it provides for uniform logging of events and (2) the default ContextListener class can be used to automatically log changes to variables, optionally with a custom logger.

**Example usage:**
```python
from mindtrace.core import ContextListener, ObservableContext

@ObservableContext(vars={"x": int, "y": int})
class MyContext:
    def __init__(self):
        self.x = 0
        self.y = 0

my_context = MyContext()
my_context.subscribe(ContextListener(autolog=["x", "y"], logger=...))  # May provide custom logger if desired

my_context.x = 1
my_context.y = 2

# Logs:
# [MyContext] x changed: 0 → 1
# [MyContext] y changed: 0 → 2  
```

### Utility Functions

#### `check_libs(*libs)`
Verify required libraries are installed.

```python
from mindtrace.core import check_libs
check_libs("numpy", "pandas")  # Raises ImportError if missing
```

#### `ifnone(value, default)`
Return default if value is None.

```python
from mindtrace.core import ifnone
result = ifnone(potentially_none_value, "default")
```

#### `instantiate_target(target, **kwargs)`
Dynamically instantiate a class from string reference.

```python
from mindtrace.core import instantiate_target
instance = instantiate_target("my.module.MyClass", param="value")
```


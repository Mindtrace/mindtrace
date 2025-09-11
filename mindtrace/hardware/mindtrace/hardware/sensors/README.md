# MindTrace Unified Sensor System

A **minimal, unified sensor system** that abstracts different communication backends (MQTT, HTTP, Serial) behind a simple async interface.

## 🚀 Quick Start

```python
from mindtrace.hardware.sensors import AsyncSensor, MQTTSensorBackend

# Create MQTT sensor
backend = MQTTSensorBackend("mqtt://localhost:1883")
async with AsyncSensor("temp001", backend, "sensors/temperature") as sensor:
    data = await sensor.read()
    print(f"Temperature: {data}")
```

## 🏗️ Architecture

```
AsyncSensor (unified interface)
    ↓
SensorBackend (abstract interface)  
    ↓
├── MQTTSensorBackend (✅ implemented)
├── HTTPSensorBackend (🔄 placeholder)
└── SerialSensorBackend (🔄 placeholder)
```

## 📖 Usage

### Single Sensor

```python
from mindtrace.hardware.sensors import AsyncSensor, MQTTSensorBackend

# Create backend
backend = MQTTSensorBackend("mqtt://broker.url:1883")

# Create sensor
sensor = AsyncSensor("sensor_id", backend, "topic/path")

# Use with context manager (recommended)
async with sensor:
    data = await sensor.read()
    
# Or manual connection
await sensor.connect()
data = await sensor.read()
await sensor.disconnect()
```

### Multiple Sensors with Manager

```python
from mindtrace.hardware.sensors import SensorManager

# Create manager
manager = SensorManager()

# Register sensors
manager.register_sensor(
    sensor_id="office_temp",
    backend_type="mqtt",
    connection_params={"broker_url": "mqtt://localhost:1883"},
    address="sensors/office/temperature"
)

manager.register_sensor(
    sensor_id="lab_humidity", 
    backend_type="mqtt",
    connection_params={"broker_url": "mqtt://localhost:1883"},
    address="sensors/lab/humidity"
)

# Bulk operations
await manager.connect_all()
readings = await manager.read_all()
await manager.disconnect_all()

# Results: {"office_temp": {...}, "lab_humidity": {...}}
```

### Backend Factory

```python
from mindtrace.hardware.sensors import create_backend, AsyncSensor

# Create backend using factory
backend = create_backend("mqtt", broker_url="mqtt://localhost:1883")
sensor = AsyncSensor("temp001", backend, "sensors/temperature")

# Supported types: "mqtt", "http", "serial"
```

## 🔧 Backend Configuration

### MQTT Backend

```python
from mindtrace.hardware.sensors import MQTTSensorBackend

backend = MQTTSensorBackend(
    broker_url="mqtt://localhost:1883",
    identifier="client_id",          # Optional
    username="user",                 # Optional  
    password="pass",                 # Optional
    keepalive=60                     # Optional
)
```

### HTTP Backend (Placeholder)

```python
from mindtrace.hardware.sensors import HTTPSensorBackend

backend = HTTPSensorBackend(
    base_url="http://api.sensors.com",
    auth_token="secret123",          # Optional
    timeout=30.0                     # Optional
)
# Note: Raises NotImplementedError until implemented
```

### Serial Backend (Placeholder)  

```python
from mindtrace.hardware.sensors import SerialSensorBackend

backend = SerialSensorBackend(
    port="/dev/ttyUSB0",
    baudrate=9600,                   # Optional
    timeout=5.0                      # Optional
)
# Note: Raises NotImplementedError until implemented
```

## 📊 Real-World Example

```python
import asyncio
from mindtrace.hardware.sensors import SensorManager

async def smart_building_monitor():
    manager = SensorManager()
    
    # Register building sensors
    sensors = [
        ("hvac_temp", "mqtt", {"broker_url": "mqtt://building.local"}, "hvac/temperature"),
        ("outdoor_weather", "http", {"base_url": "http://api.weather.com"}, "/current"),
        ("arduino_co2", "serial", {"port": "/dev/ttyUSB0"}, "READ_CO2"),
    ]
    
    for sensor_id, backend_type, params, address in sensors:
        manager.register_sensor(sensor_id, backend_type, params, address)
    
    # Monitor loop
    await manager.connect_all()
    
    while True:
        readings = await manager.read_all()
        
        for sensor_id, data in readings.items():
            if "error" not in data:
                print(f"{sensor_id}: {data}")
        
        await asyncio.sleep(30)  # Read every 30 seconds

# Run monitoring
asyncio.run(smart_building_monitor())
```

## 🧪 Testing

Test with public MQTT broker:

```python
# simulate_sensors.py - Publish fake data
from mindtrace.hardware.sensors import MQTTSensorBackend
import aiomqtt
import json

async with aiomqtt.Client("test.mosquitto.org") as client:
    data = {"temperature": 23.5, "unit": "C"}
    await client.publish("test/topic", json.dumps(data))

# read_sensors.py - Read with our system  
backend = MQTTSensorBackend("mqtt://test.mosquitto.org:1883")
async with AsyncSensor("test", backend, "test/topic") as sensor:
    data = await sensor.read()
    print(data)  # {"temperature": 23.5, "unit": "C"}
```

## 🔍 API Reference

### AsyncSensor

| Method | Description |
|--------|-------------|
| `async connect()` | Connect to backend |
| `async disconnect()` | Disconnect from backend |
| `async read()` | Read sensor data |
| `is_connected` | Connection status property |
| `sensor_id` | Sensor ID property |

### SensorManager

| Method | Description |
|--------|-------------|
| `register_sensor(id, type, params, address)` | Add sensor |
| `remove_sensor(sensor_id)` | Remove sensor |
| `get_sensor(sensor_id)` | Get sensor by ID |
| `list_sensors()` | List all sensor IDs |
| `async connect_all()` | Connect all sensors |
| `async disconnect_all()` | Disconnect all sensors |
| `async read_all()` | Read from all sensors |
| `sensor_count` | Number of sensors property |

### Backend Factory

| Function | Description |
|----------|-------------|
| `create_backend(type, **params)` | Create backend by type |
| `register_backend(name, class)` | Register custom backend |
| `get_available_backends()` | List available types |

## ⚠️ Error Handling

```python
from mindtrace.hardware.sensors import AsyncSensor, MQTTSensorBackend

backend = MQTTSensorBackend("mqtt://nonexistent:1883")
sensor = AsyncSensor("test", backend, "topic")

try:
    await sensor.connect()
except ConnectionError as e:
    print(f"Connection failed: {e}")

try:
    data = await sensor.read()
except ConnectionError as e:
    print(f"Not connected: {e}")
```

## 📁 File Structure

```
sensors/
├── __init__.py                 # Main exports
├── core/
│   ├── sensor.py               # AsyncSensor class
│   ├── manager.py              # SensorManager class  
│   └── factory.py              # Backend factory
└── backends/
    ├── base.py                 # SensorBackend interface
    ├── mqtt.py                 # MQTT implementation
    ├── http.py                 # HTTP placeholder
    └── serial.py               # Serial placeholder
```

## 🔮 Extending

### Add Custom Backend

```python
from mindtrace.hardware.sensors.backends.base import SensorBackend

class CustomSensorBackend(SensorBackend):
    async def connect(self):
        # Your connection logic
        pass
    
    async def disconnect(self):
        # Your disconnection logic  
        pass
    
    async def read_data(self, address):
        # Your data reading logic
        return {"custom": "data"}
    
    def is_connected(self):
        return True

# Register it
from mindtrace.hardware.sensors import register_backend
register_backend("custom", CustomSensorBackend)

# Use it
backend = create_backend("custom", param1="value")
```

## 🚀 What's Next

- **HTTP Backend**: REST API sensor support
- **Serial Backend**: Arduino/device communication
- **Modbus Backend**: Industrial sensor protocols
- **Advanced Features**: Caching, filtering, alerting

## 📋 Requirements

- Python 3.8+
- `aiomqtt` (for MQTT backend)
- `aiohttp` (for future HTTP backend)
- `pyserial-asyncio` (for future Serial backend)

## 🤝 Contributing

The system is designed for easy extension:

1. **New Backend**: Implement `SensorBackend` interface
2. **New Features**: Extend `AsyncSensor` or `SensorManager` 
3. **Tests**: Add to existing test suite

## 📄 License

Part of the MindTrace project.
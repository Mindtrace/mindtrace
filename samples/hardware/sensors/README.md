# Sensor System Examples

This directory contains practical examples demonstrating the MindTrace sensor system capabilities, including both data reading and publishing functionality.

## Quick Start

1. **Start MQTT Broker**:
   ```bash
   cd samples/hardware/sensors
   docker-compose up -d
   ```

2. **Terminal 1 - Publish Data**:
   ```bash
   uv run python publish_sensor_data.py
   ```

3. **Terminal 2 - Read Data**:
   ```bash
   uv run python read_sensor_data.py
   ```

4. **Clean Up**:
   ```bash
   docker-compose down
   ```

## Files

- `publish_sensor_data.py` - Demonstrates SensorSimulator publishing temperature data
- `read_sensor_data.py` - Demonstrates AsyncSensor reading temperature data  
- `docker-compose.yml` - MQTT broker setup for testing
- `mosquitto.conf` - MQTT broker configuration (anonymous access)

## What You'll See

**Publisher Output**:
```
Starting sensor data publisher...
Connected simulator: SensorSimulator(id='office_temp', backend=MQTTSensorSimulator, connected)
Published reading #1: Temperature=23.4°C, Humidity=45.2%
Published reading #2: Temperature=21.8°C, Humidity=52.1%
```

**Reader Output**:
```
Starting sensor data reader...
Connected sensor: AsyncSensor(id='office_temp', backend=MQTTSensorBackend, connected)
Received reading #1:
  Temperature: 23.4°C
  Humidity: 45.2%
  Sensor ID: office_temp_001
  Timestamp: 1699123456
```

This demonstrates the complete sensor ecosystem: simulated sensors publishing data and consumers reading it through the unified interface.
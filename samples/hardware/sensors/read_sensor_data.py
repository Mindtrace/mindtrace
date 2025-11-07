#!/usr/bin/env python3
"""
Sensor Data Reader Example

This script demonstrates how to use the AsyncSensor to read sensor data
from an MQTT broker. It subscribes to sensor topics and displays received
data in real-time, showing how the unified sensor interface works.

Usage:
    python read_sensor_data.py

Requirements:
    - MQTT broker running on localhost:1883 (use docker-compose.yml)
    - aiomqtt library installed
    - MindTrace sensor system
    - Sensor data being published (use publish_sensor_data.py)

The script will:
1. Connect to the MQTT broker as 'temp_reader'
2. Subscribe to the 'sensors/office/temperature' topic
3. Display received sensor readings in real-time
4. Show data freshness and avoid duplicate displays
5. Handle graceful shutdown on Ctrl+C
"""

import asyncio

from mindtrace.hardware.sensors import AsyncSensor, MQTTSensorBackend


async def main():
    """
    Main function that creates a sensor reader and displays data continuously.

    This function demonstrates the complete lifecycle of a sensor reader:
    - Backend creation and configuration
    - Sensor instantiation with topic subscription
    - Connection establishment
    - Continuous data reading loop with duplicate filtering
    - Graceful cleanup on shutdown
    """
    print("Starting sensor data reader...")

    # Create MQTT sensor backend for reading data
    # The identifier makes this client unique on the MQTT broker
    backend = MQTTSensorBackend(broker_url="mqtt://localhost:1883", identifier="temp_reader")

    # Create async sensor instance
    # This represents a client reading from a temperature sensor
    sensor = AsyncSensor(sensor_id="office_temp", backend=backend, address="sensors/office/temperature")

    try:
        # Establish connection to the MQTT broker
        await sensor.connect()
        print(f"Connected sensor: {sensor}")
        print("Listening for sensor data (Press Ctrl+C to stop)...")
        print("-" * 60)

        # Track the last received sequence to avoid duplicate displays
        last_sequence = None

        # Main reading loop
        while True:
            # Attempt to read the latest sensor data
            data = await sensor.read()

            if data:
                # Extract key fields from sensor data
                sequence = data.get("sequence", "unknown")
                temperature = data.get("temperature", "N/A")
                humidity = data.get("humidity", "N/A")
                timestamp = data.get("timestamp", "N/A")
                sensor_id = data.get("sensor_id", "N/A")

                # Only display new data to avoid spam
                if sequence != last_sequence:
                    print(f"Received reading #{sequence}:")
                    print(f"  Temperature: {temperature}°C")
                    print(f"  Humidity: {humidity}%")
                    print(f"  Sensor ID: {sensor_id}")
                    print(f"  Timestamp: {timestamp}")
                    print("-" * 40)
                    last_sequence = sequence
                else:
                    # Show that we're actively listening but no new data
                    print("Waiting for new sensor data...")
            else:
                # No data available yet (normal for first few seconds)
                print("No sensor data received yet, waiting...")

            # Poll every second for new data
            await asyncio.sleep(1)

    except KeyboardInterrupt:
        print("\nShutdown requested by user...")

    except ConnectionError as e:
        print(f"Connection failed: {e}")
        print("Make sure MQTT broker is running on localhost:1883")

    except Exception as e:
        print(f"Unexpected error: {e}")

    finally:
        # Clean up connection
        await sensor.disconnect()
        print("Sensor reader disconnected successfully")


if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main())

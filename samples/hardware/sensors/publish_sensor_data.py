#!/usr/bin/env python3
"""
Sensor Data Publisher Example

This script demonstrates how to use the SensorSimulator to publish sensor data
to an MQTT broker. It simulates a temperature and humidity sensor by publishing
realistic data every 2 seconds to the 'sensors/office/temperature' topic.

Usage:
    python publish_sensor_data.py

Requirements:
    - MQTT broker running on localhost:1883 (use docker-compose.yml)
    - aiomqtt library installed
    - MindTrace sensor system

The script will:
1. Connect to the MQTT broker as 'temp_simulator'
2. Publish temperature and humidity readings every 2 seconds
3. Include timestamps and sequence numbers for tracking
4. Handle graceful shutdown on Ctrl+C
"""

import asyncio
import random
import time

from mindtrace.hardware.sensors import MQTTSensorSimulator, SensorSimulator


async def main():
    """
    Main function that creates a sensor simulator and publishes data continuously.

    This function demonstrates the complete lifecycle of a sensor simulator:
    - Backend creation and configuration
    - Simulator instantiation with topic assignment
    - Connection establishment
    - Continuous data publishing loop
    - Graceful cleanup on shutdown
    """
    print("Starting sensor data publisher...")

    # Create MQTT simulator backend
    # The identifier makes this client unique on the MQTT broker
    backend = MQTTSensorSimulator(broker_url="mqtt://localhost:1883", identifier="temp_simulator")

    # Create sensor simulator instance
    # This represents a temperature sensor in an office environment
    simulator = SensorSimulator(simulator_id="office_temp", backend=backend, address="sensors/office/temperature")

    try:
        # Establish connection to the MQTT broker
        await simulator.connect()
        print(f"Connected simulator: {simulator}")
        print("Publishing sensor data (Press Ctrl+C to stop)...")

        # Main publishing loop
        sequence_number = 0
        while True:
            sequence_number += 1

            # Generate realistic sensor readings
            # Temperature: 15-30°C with some variation
            # Humidity: 30-70% relative humidity
            temperature = round(20 + random.uniform(-5, 10), 1)
            humidity = round(random.uniform(30, 70), 1)

            # Create structured sensor data payload
            sensor_data = {
                "temperature": temperature,
                "humidity": humidity,
                "unit": "C",
                "timestamp": int(time.time()),
                "sequence": sequence_number,
                "sensor_id": "office_temp_001",
            }

            # Publish data to MQTT topic
            await simulator.publish(sensor_data)
            print(f"Published reading #{sequence_number}: Temperature={temperature}°C, Humidity={humidity}%")

            # Wait before next reading (simulate sensor sampling rate)
            await asyncio.sleep(2)

    except KeyboardInterrupt:
        print("\nShutdown requested by user...")

    except ConnectionError as e:
        print(f"Connection failed: {e}")
        print("Make sure MQTT broker is running on localhost:1883")

    except Exception as e:
        print(f"Unexpected error: {e}")

    finally:
        # Clean up connection
        await simulator.disconnect()
        print("Sensor simulator disconnected successfully")


if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main())

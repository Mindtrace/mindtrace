import logging
import multiprocessing as mp
import random
import time

from mindtrace.registry import MinioRegistryBackend, Registry

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_registry():
    """Create a new Registry instance with MinIO backend."""
    backend = MinioRegistryBackend(
        endpoint="localhost:9000",
        access_key="minioadmin",
        secret_key="minioadmin",
        bucket="mindtrace-registry",
        secure=False,
    )
    return Registry(backend=backend)


def simulate_concurrent_saves(process_id: int, num_operations: int):
    """Simulate a process performing multiple save operations."""
    registry = create_registry()

    for i in range(num_operations):
        try:
            # Randomly choose between saving a new version or updating existing
            if random.random() < 0.3:  # 30% chance to update existing
                # Try to update an existing object
                try:
                    # First check if the object exists
                    if not registry.has_object("concurrent:test"):
                        logger.warning(f"Process {process_id}: Object concurrent:test does not exist")
                        continue

                    obj = registry.load("concurrent:test")
                    new_value = obj + 1
                    registry.save("concurrent:test", new_value)
                    logger.info(f"Process {process_id}: Updated value to {new_value}")
                except ValueError as e:
                    logger.warning(f"Process {process_id}: {e}")
            else:
                # Save a new object with random name
                obj_name = f"concurrent:test:{random.randint(1, 5)}"
                value = random.randint(1, 100)
                registry.save(obj_name, value)
                logger.info(f"Process {process_id}: Saved {obj_name} with value {value}")

            # Random delay to simulate work
            time.sleep(random.uniform(0.1, 0.5))

        except Exception as e:
            logger.error(f"Process {process_id}: Error during operation: {e}")


def main():
    # Create initial registry and test object
    registry = create_registry()
    registry.save("concurrent:test", 1)
    logger.info("Created initial test object")

    # Number of processes and operations
    num_processes = 4
    operations_per_process = 5

    # Create and start processes
    processes = []
    for i in range(num_processes):
        p = mp.Process(target=simulate_concurrent_saves, args=(i, operations_per_process))
        processes.append(p)
        p.start()

    # Wait for all processes to complete
    for p in processes:
        p.join()

    # Verify final state
    try:
        final_value = registry.load("concurrent:test")
        logger.info(f"Final value of concurrent:test: {final_value}")

        # List all objects and their versions
        logger.info("\nFinal registry state:")
        print(registry.__str__(latest_only=False))

    except Exception as e:
        logger.error(f"Error verifying final state: {e}")


if __name__ == "__main__":
    main()

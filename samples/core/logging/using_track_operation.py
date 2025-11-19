import asyncio

from mindtrace.core.logging.logger import get_logger, track_operation


# Example 1: Context manager usage
async def context_manager_example():
    """Demonstrate track_operation as context manager."""
    async with track_operation("fetch_data", timeout=5.0, user_id="123") as log:
        await asyncio.sleep(0.2)
        log.info("data_fetched", records=42)

    custom_logger = get_logger("my_service", use_structlog=True)
    async with track_operation("fetch_data", timeout=5.0, logger=custom_logger, user_id="123") as log:
        await asyncio.sleep(0.2)
        log.info("data_fetched", records=42)


# Example 2: Decorator usage async
@track_operation("aprocess_data", batch_id="batch_123", timeout=3.0, include_system_metrics=True)
async def aprocess_data(data: list) -> list:
    """Process data with automatic logging."""
    await asyncio.sleep(0.1)
    return [item.upper() for item in data]


# Example 3: Decorator usage sync
@track_operation("process_data", batch_id="batch_123", timeout=3.0)
def process_data(data: list) -> list:
    """Process data with automatic logging."""
    return [item.upper() for item in data]


# Example 4: Class method decorator
class DataProcessor:
    def __init__(self):
        self.logger = get_logger("data_processor", use_structlog=True)
        self.logger.info("Data processor initialized")

    @track_operation("process_batch", include_args=["batch_id"], timeout=2.0)
    async def process_batch(self, batch_id: str, data: list):
        """Process batch with automatic logging."""
        await asyncio.sleep(0.1)  # Simulate processing
        return [item.upper() for item in data]

    @classmethod
    @track_operation("classmethod_process_batch", include_args=["batch_id"], timeout=2.0)
    def process_batch_classmethod(cls, batch_id: str, data: list):
        """Process batch with automatic logging."""
        return [item.upper() for item in data]


async def main():
    print("=== Context Manager Usage ===")
    await context_manager_example()

    print("\n=== Decorator Usage async ===")
    result = await aprocess_data(["hello", "world"])
    print(f"Processed: {result}")

    print("\n=== Decorator Usage Sync ===")
    result = process_data(["hello", "world"])
    print(f"Processed: {result}")

    print("\n=== Instance Method Decorator Usage ===")
    processor = DataProcessor()
    result = await processor.process_batch("batch_456", ["test", "data"])
    print(f"Batch processed: {result}")

    print("\n=== Class Method Decorator Usage ====")
    result = DataProcessor.process_batch_classmethod("batch_456", ["test", "data"])
    print(f"Batch processed: {result}")


if __name__ == "__main__":
    asyncio.run(main())

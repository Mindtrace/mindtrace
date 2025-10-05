import asyncio
from mindtrace.core.logging.logger import track_operation, get_logger

async def main():
    async with track_operation("fetch_data", timeout=5.0, user_id="123") as log:
        await asyncio.sleep(0.2)  # your async work here
        log.info("data_fetched", records=42)
    
    custom_logger = get_logger("my_service", use_structlog=True)
    async with track_operation("fetch_data", timeout=5.0, logger=custom_logger, user_id="123") as log:
        await asyncio.sleep(0.2)  # your async work here
        log.info("data_fetched", records=42)

if __name__ == "__main__":
    asyncio.run(main())
#!/usr/bin/env python3
"""
Comprehensive example demonstrating Mindtrace autologger with:
- Structlog vs Stdlib logging formats
- Sync vs Async functions
- Instance methods vs Class methods
- Error handling scenarios
- System metrics collection (CPU, memory, performance)
- Duration tracking and execution time measurement
"""

import asyncio
import logging
import time
from mindtrace.core import Mindtrace

# Setup stdlib logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(name)s: %(message)s'
)

# Setup structlog (if available)
try:
    import structlog
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    STRUCTLOG_AVAILABLE = True
except ImportError:
    STRUCTLOG_AVAILABLE = False
    print("Note: structlog not available, using stdlib logging only")

class DataProcessor(Mindtrace):
    """Data processor with both stdlib and structlog support."""
    
    def __init__(self, use_structlog=False):
        super().__init__(use_structlog=use_structlog)

    # ===== INSTANCE METHODS =====
    
    @Mindtrace.autolog(include_system_metrics=True)
    def process_data_sync(self, data_list, batch_size=100, multiplier=2):
        """Synchronous instance method - processes data in batches with system metrics."""
        self.logger.info(f"Processing {len(data_list)} items in batches of {batch_size}")
        
        results = []
        for i in range(0, len(data_list), batch_size):
            batch = data_list[i:i + batch_size]
            batch_result = self._process_batch_sync(batch, multiplier)
            results.extend(batch_result)
            self.logger.info(f"Processed batch {i//batch_size + 1}")
        
        return results

    @Mindtrace.autolog(include_system_metrics=True, include_duration=True)
    async def process_data_async(self, data_list, batch_size=100, multiplier=2):
        """Asynchronous instance method - processes data with async operations and metrics."""
        self.logger.info(f"Async processing {len(data_list)} items in batches of {batch_size}")
        
        results = []
        for i in range(0, len(data_list), batch_size):
            batch = data_list[i:i + batch_size]
            # Simulate async I/O operation
            await asyncio.sleep(0.01)
            batch_result = await self._process_batch_async(batch, multiplier)
            results.extend(batch_result)
            self.logger.info(f"Async processed batch {i//batch_size + 1}")
        
        return results

    @Mindtrace.autolog(include_duration=True)
    def _process_batch_sync(self, batch, multiplier=2):
        """Private synchronous method with duration tracking."""
        time.sleep(0.01)  # Simulate processing time
        return [item * multiplier for item in batch]

    @Mindtrace.autolog(include_duration=True)
    async def _process_batch_async(self, batch, multiplier=2):
        """Private asynchronous method with duration tracking."""
        await asyncio.sleep(0.01)  # Simulate async processing
        return [item * multiplier for item in batch]

    @Mindtrace.autolog(include_system_metrics=True, include_duration=True)
    def method_with_error(self, value, should_fail=True):
        """Method that can raise an error for testing exception handling with metrics."""
        if should_fail:
            raise ValueError(f"Intentional error for value: {value}")
        return f"Success: {value}"

    # ===== CLASS METHODS =====
    
    @classmethod
    @Mindtrace.autolog(include_system_metrics=True)
    def get_processor_info(cls):
        """Class method with system metrics - can be called without an instance."""
        cls.logger.info("Getting processor information")
        return {
            "class_name": cls.__name__,
            "module": cls.__module__,
            "description": "Data processor for batch operations",
            "features": ["sync", "async", "error_handling", "metrics"]
        }

    @classmethod
    @Mindtrace.autolog(include_system_metrics=True, include_duration=True)
    async def async_class_method(cls, data):
        """Async class method with metrics and duration tracking."""
        cls.logger.info("Running async class method")
        await asyncio.sleep(0.01)
        return {"processed_by": cls.__name__, "data_length": len(data)}

# ===== DEMONSTRATION FUNCTIONS =====

def demonstrate_stdlib_logging():
    """Demonstrate stdlib logging format."""
    print("\n" + "="*80)
    print("STDLIB LOGGING FORMAT (Verbose)")
    print("="*80)
    
    processor = DataProcessor(use_structlog=False)
    
    # Test sync instance method
    print("\n1. Sync Instance Method:")
    data = list(range(10))
    result = processor.process_data_sync(data, batch_size=3, multiplier=3)
    print(f"   Result: {result[:5]}... (showing first 5 items)")
    
    # Test error handling
    print("\n2. Error Handling:")
    try:
        processor.method_with_error("test", should_fail=True)
    except ValueError as e:
        print(f"   Caught expected error: {e}")
    
    # Test class method
    print("\n3. Class Method:")
    info = DataProcessor.get_processor_info()
    print(f"   Info: {info}")

def demonstrate_structlog_logging():
    """Demonstrate structlog logging format."""
    if not STRUCTLOG_AVAILABLE:
        print("\n" + "="*80)
        print("STRUCTLOG NOT AVAILABLE - SKIPPING")
        print("="*80)
        return
    
    print("\n" + "="*80)
    print("STRUCTLOG LOGGING FORMAT (Structured JSON)")
    print("="*80)
    
    processor = DataProcessor(use_structlog=True)
    
    # Test sync instance method
    print("\n1. Sync Instance Method:")
    data = list(range(5))
    result = processor.process_data_sync(data, batch_size=2, multiplier=4)
    print(f"   Result: {result}")

    # Test error handling
    print("\n2. Error Handling:")
    try:
        processor.method_with_error("test", should_fail=True)
    except ValueError as e:
        print(f"   Caught expected error: {e}")
    
    # Test class method
    print("\n3. Class Method:")
    info = DataProcessor.get_processor_info()
    print(f"   Info: {info}")

async def demonstrate_async_operations():
    """Demonstrate async operations."""
    print("\n" + "="*80)
    print("ASYNC OPERATIONS")
    print("="*80)
    
    processor = DataProcessor(use_structlog=False)
    
    # Test async instance method
    print("\n1. Async Instance Method:")
    data = list(range(8))
    result = await processor.process_data_async(data, batch_size=3, multiplier=5)
    print(f"   Result: {result}")
    
    # Test async class method
    print("\n2. Async Class Method:")
    result = await DataProcessor.async_class_method(data)
    print(f"   Result: {result}")

def demonstrate_system_metrics():
    """Demonstrate system metrics collection."""
    print("\n" + "="*80)
    print("SYSTEM METRICS COLLECTION")
    print("="*80)
    
    processor = DataProcessor(use_structlog=False)
    
    # Test with system metrics enabled
    print("\n1. Processing with System Metrics:")
    data = list(range(20))
    result = processor.process_data_sync(data, batch_size=5, multiplier=3)
    print(f"   Result: {result[:5]}... (showing first 5 items)")
    
    # Test error handling with metrics
    print("\n2. Error Handling with Metrics:")
    try:
        processor.method_with_error("test_metrics", should_fail=True)
    except ValueError as e:
        print(f"   Caught expected error: {e}")
    
    # Test class method with metrics
    print("\n3. Class Method with Metrics:")
    info = DataProcessor.get_processor_info()
    print(f"   Info: {info}")

async def main():
    """Main demonstration function."""
    print("MINTRACE AUTOLOGGER COMPREHENSIVE DEMONSTRATION")
    print("="*80)
    
    # Demonstrate stdlib logging
    demonstrate_stdlib_logging()
    
    # Demonstrate structlog logging
    demonstrate_structlog_logging()
    
    # Demonstrate async operations
    await demonstrate_async_operations()
    
    # Demonstrate system metrics
    demonstrate_system_metrics()

    print("\n" + "="*80)
    print("DEMONSTRATION COMPLETE")
    print("="*80)
    print("Key Features Demonstrated:")
    print("Stdlib logging: Verbose, human-readable format")
    print("Structlog logging: Structured JSON format (if available)")
    print("Sync functions: Instance methods, class methods")
    print("Async functions: Instance methods, class methods")
    print("Error handling: Automatic exception logging with stack traces")
    print("Duration tracking: Automatic execution time measurement")
    print("System metrics: CPU, memory, and performance monitoring")
    print("Flexible configuration: Custom formatters, log levels, metrics")

if __name__ == "__main__":
    asyncio.run(main())
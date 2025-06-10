"""
Example demonstrating the new Consumer class that automatically creates ConsumerBackends.

This shows how Consumer.connect(orchestrator) automatically creates the appropriate
ConsumerBackend (LocalConsumerBackend, RedisConsumerBackend, etc.) based on the
orchestrator's backend type.
"""

from mindtrace.jobs.mindtrace.queue_management.orchestrator import Orchestrator
from mindtrace.jobs.mindtrace.queue_management.local.client import LocalClient
from mindtrace.jobs.mindtrace.queue_management.redis.client import RedisClient
from mindtrace.jobs.mindtrace.queue_management.rabbitmq.client import RabbitMQClient
from mindtrace.jobs.mindtrace.consumer import Consumer
from mindtrace.jobs.mindtrace.types import JobSchema, Job, JobInput, JobOutput
from mindtrace.jobs.mindtrace.utils import job_from_schema
import logging
import traceback


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Define job input/output types
class ObjectDetectionInput(JobInput):
    """Input for object detection jobs."""
    image_path: str = ""
    model: str = "yolo_v8"


class ObjectDetectionOutput(JobOutput):
    """Output for object detection jobs."""
    detections: list = []
    confidence: float = 0.0


class DataProcessingInput(JobInput):
    """Input for data processing jobs."""
    dataset_id: str = ""
    processing_type: str = ""


class DataProcessingOutput(JobOutput):
    """Output for data processing jobs."""
    processed_count: int = 0
    output_path: str = ""


# Define Job Schemas
customer_a_schema = JobSchema(
    name="customer_a_line_4_object_detection",
    input=ObjectDetectionInput(),
    output=ObjectDetectionOutput()
)

customer_b_schema = JobSchema(
    name="customer_b_data_processing", 
    input=DataProcessingInput(),
    output=DataProcessingOutput()
)


# Example Consumer implementations
class CustomerAObjectDetectionConsumer(Consumer):
    """Consumer for Customer A's object detection jobs."""
    
    def run(self, job: Job) -> None:
        logger.info(f"[CustomerA] Processing object detection job {job.id}")
        logger.info(f"[CustomerA] Job input: {job.payload.input}")
        logger.info(f"[CustomerA] Schema: {job.schema_name}")
        # Simulate object detection processing...
        logger.info(f"[CustomerA] Object detection complete for job {job.id}")


class CustomerBDataProcessingConsumer(Consumer):
    """Consumer for Customer B's data processing jobs."""
    
    def run(self, job: Job) -> None:
        logger.info(f"[CustomerB] Processing data job {job.id}")
        logger.info(f"[CustomerB] Job input: {job.payload.input}")
        logger.info(f"[CustomerB] Schema: {job.schema_name}")
        # Simulate data processing...
        logger.info(f"[CustomerB] Data processing complete for job {job.id}")


def test_backend(backend_name: str, orchestrator: Orchestrator, test_connection: bool = True):
    """Test the Consumer API with a specific backend."""
    try:
        logger.info(f"\n--- Testing {backend_name} Backend ---")
        
        # Test connection if requested
        if test_connection and hasattr(orchestrator.backend, 'connection'):
            try:
                # This will fail gracefully if service isn't running
                orchestrator.backend.connection.connect()
                logger.info(f"✓ {backend_name} connection successful")
            except Exception as e:
                logger.warning(f"✗ {backend_name} connection failed: {str(e)}")
                return {"backend": backend_name, "status": "connection_failed", "error": str(e)}
        
        # Register schemas (creates queues)
        logger.info(f"Registering schemas with {backend_name}...")
        orchestrator.register(customer_a_schema)
        orchestrator.register(customer_b_schema)
        
        # Create Consumer instances - note they're not connected yet
        logger.info("Creating Consumer instances...")
        customer_a_consumer = CustomerAObjectDetectionConsumer("customer_a_line_4_object_detection")
        customer_b_consumer = CustomerBDataProcessingConsumer("customer_b_data_processing")
        
        # Connect consumers to orchestrator - this automatically creates ConsumerBackends!
        logger.info(f"Connecting consumers to {backend_name} orchestrator...")
        customer_a_consumer.connect(orchestrator)
        customer_b_consumer.connect(orchestrator)
        
        logger.info(f"✓ Consumer backends created: {type(customer_a_consumer.consumer_backend).__name__}")
        
        # Create and publish jobs
        logger.info("Creating and publishing jobs...")
        job_a1 = job_from_schema(customer_a_schema, ObjectDetectionInput(
            image_path="/path/to/image1.jpg", 
            model="yolo_v8"
        ))
        job_a2 = job_from_schema(customer_a_schema, ObjectDetectionInput(
            image_path="/path/to/image2.jpg", 
            model="yolo_v8"
        ))
        job_b1 = job_from_schema(customer_b_schema, DataProcessingInput(
            dataset_id="ds_001", 
            processing_type="aggregate"
        ))
        job_b2 = job_from_schema(customer_b_schema, DataProcessingInput(
            dataset_id="ds_002", 
            processing_type="transform"
        ))
        
        # Publish to appropriate queues
        orchestrator.publish("customer_a_line_4_object_detection", job_a1)
        orchestrator.publish("customer_a_line_4_object_detection", job_a2)
        orchestrator.publish("customer_b_data_processing", job_b1)
        orchestrator.publish("customer_b_data_processing", job_b2)
        
        logger.info("✓ Jobs published successfully")
        
        # Show queue states
        a_count = orchestrator.count_queue_messages("customer_a_line_4_object_detection")
        b_count = orchestrator.count_queue_messages("customer_b_data_processing")
        logger.info(f"Queue states - CustomerA: {a_count} jobs, CustomerB: {b_count} jobs")
        
        # Consumer A processes their jobs
        logger.info("CustomerA consumer processing jobs...")
        customer_a_consumer.consume(num_messages=2)
        
        # Consumer B processes their jobs
        logger.info("CustomerB consumer processing jobs...")
        customer_b_consumer.consume(num_messages=2)
        
        # Verify queues are empty
        a_count_after = orchestrator.count_queue_messages("customer_a_line_4_object_detection")
        b_count_after = orchestrator.count_queue_messages("customer_b_data_processing")
        logger.info(f"Final queue states - CustomerA: {a_count_after} jobs, CustomerB: {b_count_after} jobs")
        
        return {
            "backend": backend_name,
            "status": "success",
            "consumer_backend_type": type(customer_a_consumer.consumer_backend).__name__,
            "jobs_processed": {
                "customer_a": 2,
                "customer_b": 2
            }
        }
        
    except Exception as e:
        logger.error(f"✗ {backend_name} test failed: {str(e)}")
        logger.error(traceback.format_exc())
        return {"backend": backend_name, "status": "error", "error": str(e)}


def main():
    """Test the new Consumer pattern with different backends."""
    logger.info("=== Testing Consumer.connect() with ConsumerBackend Pattern ===")
    
    results = {}
    
    # Test Local Backend (always available)
    logger.info("\n🔄 Testing Local Backend...")
    local_backend = LocalClient()
    local_orchestrator = Orchestrator(local_backend)
    results['Local'] = test_backend("Local", local_orchestrator, False)
    
    # Test Redis Backend (if available)
    logger.info("\n🔄 Testing Redis Backend...")
    try:
        redis_backend = RedisClient(host="localhost", port=6379, db=0)
        redis_orchestrator = Orchestrator(redis_backend)
        results['Redis'] = test_backend("Redis", redis_orchestrator, True)
    except Exception as e:
        logger.warning(f"Redis backend creation failed: {str(e)}")
        results['Redis'] = {"backend": "Redis", "status": "creation_failed", "error": str(e)}
    
    # Test RabbitMQ Backend (if available)
    logger.info("\n🔄 Testing RabbitMQ Backend...")
    try:
        rabbitmq_backend = RabbitMQClient(
            host="localhost", 
            port=5672, 
            username="user", 
            password="password"
        )
        rabbitmq_orchestrator = Orchestrator(rabbitmq_backend)
        results['RabbitMQ'] = test_backend("RabbitMQ", rabbitmq_orchestrator, True)
    except Exception as e:
        logger.warning(f"RabbitMQ backend creation failed: {str(e)}")
        results['RabbitMQ'] = {"backend": "RabbitMQ", "status": "creation_failed", "error": str(e)}
    
    # Summary
    logger.info("\n" + "="*60)
    logger.info("CONSUMER.CONNECT() PATTERN DEMO RESULTS")
    logger.info("="*60)
    
    for backend_name, result in results.items():
        status = result.get('status', 'unknown')
        if status == 'success':
            consumer_backend = result.get('consumer_backend_type', 'unknown')
            logger.info(f"✓ {backend_name:>10}: {status} - Created {consumer_backend}")
        else:
            logger.info(f"✗ {backend_name:>10}: {status}")
    
    logger.info("\n🎯 Key Architectural Benefits Demonstrated:")
    logger.info("   • Consumer.connect(orchestrator) automatically creates appropriate ConsumerBackend")
    logger.info("   • Same Consumer API works across Local, Redis, RabbitMQ backends")
    logger.info("   • ConsumerBackend handles backend-specific message consumption")
    logger.info("   • Clean separation: Consumer (user API) vs ConsumerBackend (infrastructure)")
    logger.info("   • User only implements run(job) method")


if __name__ == "__main__":
    main() 
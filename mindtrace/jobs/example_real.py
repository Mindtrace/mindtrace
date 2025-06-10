"""
Example demonstrating the new Consumer API and JobSchema-based routing system
using ALL real backend implementations: Local, Redis, and RabbitMQ.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from pydantic import BaseModel
from typing import List, Dict, Any
from mindtrace.consumer import Consumer
from mindtrace.queue_management.orchestrator import Orchestrator
from mindtrace.queue_management.local.client import LocalClient
from mindtrace.queue_management.redis.client import RedisClient
from mindtrace.queue_management.rabbitmq.client import RabbitMQClient
from mindtrace.types import JobSchema, JobInput, JobOutput, Job
from mindtrace.utils import job_from_schema


# Define specific input/output models for different job types
class ObjectDetectionInput(JobInput):
    """Input for object detection jobs."""
    image_path: str
    confidence_threshold: float = 0.5
    model_name: str = "yolov8"
    customer_id: str
    production_line: str


class ObjectDetectionOutput(JobOutput):
    """Output for object detection jobs."""
    detections: List[Dict[str, Any]]
    processing_time: float
    model_version: str


class DataProcessingInput(JobInput):
    """Input for data processing jobs."""
    dataset_path: str
    processing_type: str
    batch_size: int = 100
    filters: Dict[str, Any] = {}


class DataProcessingOutput(JobOutput):
    """Output for data processing jobs."""
    processed_records: int
    output_path: str
    errors: List[str] = []


# Define specialized Consumer classes
class CustomerALine4Consumer(Consumer):
    """Consumer for Customer A Line 4 object detection jobs."""
    
    def __init__(self):
        super().__init__("customer_a_line_4_object_detection")
    
    def run(self, job: Job) -> None:
        """Process Customer A Line 4 object detection job."""
        print(f"🔍 Processing Customer A Line 4 object detection job: {job.id}")
        
        # Extract input data
        input_data = job.payload.input
        if isinstance(input_data, ObjectDetectionInput):
            print(f"   📷 Image: {input_data.image_path}")
            print(f"   🎯 Confidence: {input_data.confidence_threshold}")
            print(f"   🏭 Customer: {input_data.customer_id}, Line: {input_data.production_line}")
            
            # Simulate processing
            print("   ⚙️ Running object detection...")
            print("   ✅ Object detection completed!")


class CustomerBDataProcessingConsumer(Consumer):
    """Consumer for Customer B data processing jobs."""
    
    def __init__(self):
        super().__init__("customer_b_data_processing")
    
    def run(self, job: Job) -> None:
        """Process Customer B data processing job."""
        print(f"📊 Processing Customer B data processing job: {job.id}")
        
        # Extract input data
        input_data = job.payload.input
        if isinstance(input_data, DataProcessingInput):
            print(f"   📁 Dataset: {input_data.dataset_path}")
            print(f"   🔧 Processing type: {input_data.processing_type}")
            print(f"   📦 Batch size: {input_data.batch_size}")
            
            # Simulate processing
            print("   ⚙️ Processing data...")
            print("   ✅ Data processing completed!")


def test_backend(backend_name: str, backend_client, test_redis_rabbitmq: bool = False):
    """Test a specific backend implementation."""
    print(f"\n{'='*50}")
    print(f"🚀 Testing {backend_name} Backend")
    print(f"{'='*50}")
    
    try:
        # 1. Create orchestrator with the specific backend
        print(f"1️⃣ Setting up orchestrator with {backend_name} backend...")
        orchestrator = Orchestrator(backend_client)
        print(f"   ✅ Real orchestrator created with {backend_name} backend\n")
        
        # 2. Define JobSchemas for different types of work
        print("2️⃣ Defining JobSchemas...")
        
        # Schema for Customer A Line 4 object detection
        customer_a_line_4_schema = JobSchema(
            name="customer_a_line_4_object_detection",
            input=ObjectDetectionInput(
                image_path="",
                customer_id="customer_a", 
                production_line="line_4"
            ),
            output=ObjectDetectionOutput(
                detections=[],
                processing_time=0.0,
                model_version=""
            )
        )
        
        # Schema for Customer B data processing
        customer_b_data_schema = JobSchema(
            name="customer_b_data_processing",
            input=DataProcessingInput(
                dataset_path="",
                processing_type=""
            ),
            output=DataProcessingOutput(
                processed_records=0,
                output_path=""
            )
        )
        
        print(f"   📋 Schema 1: {customer_a_line_4_schema.name}")
        print(f"   📋 Schema 2: {customer_b_data_schema.name}")
        print("   ✅ JobSchemas defined\n")
        
        # 3. Register schemas with orchestrator
        print(f"3️⃣ Registering schemas with {backend_name} orchestrator...")
        queue_1 = orchestrator.register(customer_a_line_4_schema)
        queue_2 = orchestrator.register(customer_b_data_schema)
        print(f"   🗂️ {backend_name} queue created for schema 1: {queue_1}")
        print(f"   🗂️ {backend_name} queue created for schema 2: {queue_2}")
        print(f"   ✅ Schemas registered with {backend_name} backend\n")
        
        # 4. Create and connect consumers
        print(f"4️⃣ Creating and connecting consumers to {backend_name}...")
        
        consumer_a = CustomerALine4Consumer()
        consumer_b = CustomerBDataProcessingConsumer()
        
        consumer_a.connect(orchestrator)
        consumer_b.connect(orchestrator)
        
        print(f"   🤖 Consumer A connected to {backend_name} queue: {consumer_a.queue_name}")
        print(f"   🤖 Consumer B connected to {backend_name} queue: {consumer_b.queue_name}")
        print(f"   ✅ Consumers connected to {backend_name} orchestrator\n")
        
        # 5. Create jobs using job_from_schema utility
        print("5️⃣ Creating jobs using job_from_schema utility...")
        
        # Create Customer A Line 4 job
        detection_input = ObjectDetectionInput(
            image_path=f"/data/customer_a/line_4/image_{backend_name.lower()}.jpg",
            confidence_threshold=0.7,
            model_name="yolov8n",
            customer_id="customer_a",
            production_line="line_4"
        )
        detection_job = job_from_schema(customer_a_line_4_schema, detection_input)
        
        # Create Customer B data processing job
        processing_input = DataProcessingInput(
            dataset_path=f"/data/customer_b/batch_{backend_name.lower()}.csv",
            processing_type="feature_extraction",
            batch_size=50,
            filters={"status": "active", "type": "sensor_data", "backend": backend_name.lower()}
        )
        processing_job = job_from_schema(customer_b_data_schema, processing_input)
        
        print(f"   📄 Created detection job for {backend_name}: {detection_job.id}")
        print(f"   📄 Created processing job for {backend_name}: {processing_job.id}")
        print(f"   ✅ Jobs created for {backend_name} using real job_from_schema utility\n")
        
        # 6. Publish jobs to appropriate queues using real backend
        print(f"6️⃣ Publishing jobs to {backend_name} queues...")
        
        job_id_1 = orchestrator.publish(queue_1, detection_job)
        job_id_2 = orchestrator.publish(queue_2, processing_job)
        
        print(f"   📤 Published detection job to {backend_name} queue: {queue_1} (ID: {job_id_1})")
        print(f"   📤 Published processing job to {backend_name} queue: {queue_2} (ID: {job_id_2})")
        print(f"   ✅ Jobs published to {backend_name} backend\n")
        
        # 7. Check queue status
        print(f"7️⃣ Checking {backend_name} queue status...")
        queue_1_count = orchestrator.count_queue_messages(queue_1)
        queue_2_count = orchestrator.count_queue_messages(queue_2)
        print(f"   📊 {backend_name} queue {queue_1} has {queue_1_count} messages")
        print(f"   📊 {backend_name} queue {queue_2} has {queue_2_count} messages")
        print(f"   ✅ {backend_name} queue status checked\n")
        
        # 8. Process jobs with consumers using real backend
        print(f"8️⃣ Processing jobs with {backend_name} consumers...")
        print(f"\n--- Consumer A Processing ({backend_name} Backend) ---")
        consumer_a.consume(num_messages=1)
        
        print(f"\n--- Consumer B Processing ({backend_name} Backend) ---")
        consumer_b.consume(num_messages=1)
        
        print(f"\n   ✅ Jobs processed using {backend_name} implementation\n")
        
        # 9. Check queue status after processing
        print(f"9️⃣ Checking {backend_name} queue status after processing...")
        queue_1_count_after = orchestrator.count_queue_messages(queue_1)
        queue_2_count_after = orchestrator.count_queue_messages(queue_2)
        print(f"   📊 {backend_name} queue {queue_1} now has {queue_1_count_after} messages")
        print(f"   📊 {backend_name} queue {queue_2} now has {queue_2_count_after} messages")
        print(f"   ✅ {backend_name} queues processed successfully\n")
        
        print(f"🎉 {backend_name} backend test completed successfully!")
        
        return True
        
    except Exception as e:
        print(f"❌ Error testing {backend_name} backend: {str(e)}")
        if test_redis_rabbitmq:
            print(f"   ℹ️ This is expected if {backend_name} is not running locally")
        return False


def main():
    """Demonstrate the new Consumer API with all real backend implementations."""
    print("🚀 Demonstrating new Consumer API with ALL REAL backends\n")
    print("   🏠 Local Backend (always available)")
    print("   🔴 Redis Backend (requires Redis server)")
    print("   🐰 RabbitMQ Backend (requires RabbitMQ server)")
    print("\n" + "="*60)
    
    results = {}
    
    # Test 1: Local Backend (always works)
    print("\n📦 LOCAL BACKEND TEST")
    local_backend = LocalClient()
    results['Local'] = test_backend("Local", local_backend, False)
    
    # Test 2: Redis Backend (may fail if Redis not running)
    print("\n📦 REDIS BACKEND TEST")
    try:
        redis_backend = RedisClient(host="localhost", port=6379, db=0)
        results['Redis'] = test_backend("Redis", redis_backend, True)
    except Exception as e:
        print(f"❌ Redis backend connection failed: {str(e)}")
        print("   ℹ️ Make sure Redis server is running: `redis-server`")
        results['Redis'] = False
    
    # Test 3: RabbitMQ Backend (may fail if RabbitMQ not running)
    print("\n📦 RABBITMQ BACKEND TEST")
    try:
        rabbitmq_backend = RabbitMQClient(
            host="localhost", 
            port=5672, 
            username="user", 
            password="password"
        )
        results['RabbitMQ'] = test_backend("RabbitMQ", rabbitmq_backend, True)
    except Exception as e:
        print(f"❌ RabbitMQ backend connection failed: {str(e)}")
        print("   ℹ️ Make sure RabbitMQ server is running: `sudo systemctl start rabbitmq-server`")
        results['RabbitMQ'] = False
    
    # Summary
    print("\n" + "="*60)
    print("📊 BACKEND TEST RESULTS SUMMARY")
    print("="*60)
    
    for backend, success in results.items():
        status = "✅ PASSED" if success else "❌ FAILED"
        print(f"   {backend:10} Backend: {status}")
    
    successful_backends = [name for name, success in results.items() if success]
    
    print(f"\n🎯 Summary: {len(successful_backends)}/{len(results)} backends tested successfully")
    
    if successful_backends:
        print(f"✅ Working backends: {', '.join(successful_backends)}")
    
    print("\n🔟 Key advantages demonstrated across ALL backends:")
    print("   🎯 Specific queues per customer/line combination")
    print("   🔧 No hardcoded JobType enum - fully extensible")
    print("   🤖 Simple Consumer.run() interface for job processing")
    print("   📋 JobSchema-based routing with real backends ensures type safety")
    print("   🏗️ Easy to add new job types without code changes")
    print("   🔄 Automatic queue creation when schemas are registered")
    print("   🔀 SAME API works across Local, Redis, and RabbitMQ!")
    print("   ⚡ Backend-agnostic Consumer implementation")
    print("   💾 Real message persistence across different infrastructures")
    
    print("\n1️⃣1️⃣ Clean queue names (no 'schema_' prefix) work on ALL backends:")
    print("   📂 Queue: 'customer_a_line_4_object_detection'")
    print("   📂 Queue: 'customer_b_data_processing'")
    
    print(f"\n🎉 Demo completed! The same Consumer API works seamlessly across all {len(results)} backend types!")


if __name__ == "__main__":
    main() 
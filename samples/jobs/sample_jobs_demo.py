import argparse
from pydantic import BaseModel

from mindtrace.jobs import (
    JobSchema,
    Consumer,
    Orchestrator,
    LocalClient,
    RedisClient,
    RabbitMQClient,
    job_from_schema,
)


class MathsInput(BaseModel):
    """Input model for maths operations."""

    operation: str
    a: float
    b: float


class MathsOutput(BaseModel):
    """Output model for maths operations."""

    result: float
    operation_performed: str


maths_schema = JobSchema(
    name="maths_operations",
    input=MathsInput,
    output=MathsOutput,
)


class MathsConsumer(Consumer):
    """Consumer for processing maths operations."""

    def __init__(self):
        super().__init__("maths_operations")

    def run(self, job_dict: dict) -> dict:
        """Process a maths job."""
        input_data = job_dict.get("input_data", {})
        operation = input_data.get("operation", "add")
        a = input_data.get("a")
        b = input_data.get("b")

        print(f"Processing maths job: {operation}({a}, {b})")

        if operation == "add":
            result = a + b
        elif operation == "multiply":
            result = a * b
        elif operation == "power":
            result = a**b
        else:
            raise ValueError(f"Unknown operation: {operation}")

        print(f"Maths result: {result}")

        return {
            "result": result,
            "operation_performed": f"{operation}({a}, {b}) = {result}",
        }


def setup_backend(backend_type: str):
    """Set up the appropriate backend based on the type."""
    print(f"Setting up {backend_type} backend...")
    
    backend = None
    try:
        if backend_type == "local":
            backend = LocalClient()
            print("Local backend ready")
        elif backend_type == "redis":
            backend = RedisClient(host="localhost", port=6379, db=0)
            try:
                backend.redis.ping()
                print("Redis connection verified")
            except Exception as e:
                print(f"Redis connection failed: {e}")
                if backend:
                    backend.close()
                raise
        elif backend_type == "rabbitmq":
            backend = RabbitMQClient(
                host="localhost",
                port=5672,
                username="user",
                password="password"
            )
            # Use a short timeout for connection check
            try:
                if not backend.connection.is_connected():
                    backend.connection.connect()
                print("RabbitMQ connection verified")
            except Exception as e:
                print(f"RabbitMQ connection failed: {e}")
                if backend:
                    backend.close()
                raise
        else:
            raise ValueError(f"Unknown backend type: {backend_type}")
        
        return backend
    except Exception as e:
        raise


def demo_basic_operations(orchestrator: Orchestrator):
    """Demonstrate basic queue operations."""
    print("\n=== Basic Queue Operations ===")

    print("Registering job schema...")
    maths_queue = orchestrator.register(maths_schema)
    print(f"Created queue: {maths_queue}")

    maths_jobs = [
        job_from_schema(maths_schema, MathsInput(operation="add", a=10, b=5)),
        job_from_schema(maths_schema, MathsInput(operation="multiply", a=7, b=3)),
        job_from_schema(maths_schema, MathsInput(operation="power", a=2, b=8)),
    ]

    print("Publishing maths jobs...")
    for job in maths_jobs:
        job_id = orchestrator.publish(maths_queue, job)
        print(f"  Published job {job_id}")

    maths_count = orchestrator.count_queue_messages(maths_queue)
    print(f"Queue status: {maths_queue}={maths_count}")


def demo_consumers(orchestrator: Orchestrator):
    """Demonstrate job consumption."""
    print("\n=== Job Consumption ===")

    maths_consumer = MathsConsumer()

    print("Connecting consumer...")
    maths_consumer.connect(orchestrator)

    print("Processing maths jobs...")
    maths_consumer.consume(num_messages=3, block=False)

    maths_count = orchestrator.count_queue_messages("maths_operations")
    print(f"Remaining in queue: maths_operations={maths_count}")


def demo_priority(orchestrator: Orchestrator):
    """Demonstrate priority jobs."""
    print("\n=== Priority Jobs ===")

    print("Testing priority jobs...")

    try:
        priority_queue = "maths_priority"
        print(f"Creating priority queue: {priority_queue}")

        backend_type = type(orchestrator.backend).__name__
        if backend_type == "RabbitMQClient":
            try:
                delete_result = orchestrator.backend.delete_queue(priority_queue)
                print(f"Deleted existing queue: {delete_result}")
            except Exception as e:
                print(f"No existing queue to delete: {e}")

            result = orchestrator.backend.declare_queue(
                priority_queue, max_priority=255
            )
            print("RabbitMQ priority queue (max_priority=255)")
            print(f"Queue declaration result: {result}")
        else:
            result = orchestrator.backend.declare_queue(
                priority_queue, queue_type="priority"
            )
            print(f"{backend_type} priority queue")
            print(f"Queue declaration result: {result}")

        low_priority_job = job_from_schema(
            maths_schema, MathsInput(operation="add", a=1, b=1)
        )
        high_priority_job = job_from_schema(
            maths_schema, MathsInput(operation="multiply", a=10, b=10)
        )
        urgent_job = job_from_schema(
            maths_schema, MathsInput(operation="power", a=2, b=3)
        )

        print("Publishing jobs in wrong order to test priority:")
        print("Publishing low priority job first...")
        low_id = orchestrator.publish(priority_queue, low_priority_job, priority=1)
        print(f"Job {low_id} with priority=1 (add)")

        print("Publishing medium priority job...")
        high_id = orchestrator.publish(priority_queue, high_priority_job, priority=5)
        print(f"Job {high_id} with priority=5 (multiply)")

        print("Publishing high priority job last...")
        urgent_id = orchestrator.publish(priority_queue, urgent_job, priority=10)
        print(f"Job {urgent_id} with priority=10 (power)")

        queue_count = orchestrator.count_queue_messages(priority_queue)
        print(f"All messages in queue: {queue_count}")

        import time

        time.sleep(2)

        consumer = MathsConsumer()
        consumer.connect(orchestrator)
        consumer.consume(num_messages=3, queues=[priority_queue], block=False)

        orchestrator.clean_queue(priority_queue)

    except Exception as e:
        print(f"Error: {e}")

    current_count = orchestrator.count_queue_messages("maths_operations")
    print(f"Current queue size: {current_count}")

    print("Cleaning up queue...")
    orchestrator.clean_queue("maths_operations")

    maths_count = orchestrator.count_queue_messages("maths_operations")
    print(f"After cleanup: maths_operations={maths_count}")


def main():
    parser = argparse.ArgumentParser(description="Mindtrace Jobs Demo")
    parser.add_argument(
        "--backend",
        choices=["local", "redis", "rabbitmq"],
        default="local",
        help="Backend to use for the demo (default: local)",
    )
    args = parser.parse_args()
    print(f"Using backend: {args.backend}")

    backend = None
    orchestrator = None
    try:
        backend = setup_backend(args.backend)
        orchestrator = Orchestrator(backend)

        demo_basic_operations(orchestrator)
        demo_consumers(orchestrator)
        demo_priority(orchestrator)

    except Exception as e:
        print(f"Error: {e}")
        return 1

    return 0


if __name__ == "__main__":
    main()

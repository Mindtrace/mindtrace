import time

import pytest

from mindtrace.jobs import Consumer, JobSchema, LocalClient, Orchestrator



class TestConsumer:
    """Test Consumer functionality with dict-based messages."""

    def setup_method(self):
        pass

    def test_consumer_basic_functionality(self, temp_local_client, sample_job_input, sample_job_output, create_test_job_fixture):
        """Test basic consumer message processing."""

        orchestrator = Orchestrator(backend=temp_local_client)
        test_schema = JobSchema(name="test-consumer-jobs", input_schema=sample_job_input, output_schema=sample_job_output)
        test_queue = orchestrator.register(test_schema)

        class TestWorker(Consumer):
            def __init__(self, name):
                super().__init__()
                self.processed_jobs = []

            def run(self, job_dict):
                self.processed_jobs.append(job_dict)
                payload = job_dict.get("payload", {})
                task_data = payload.get("data", "unknown")
                return {"result": f"processed_{task_data}"}

        consumer = TestWorker("test_consumer_jobs")
        consumer.connect_to_orchestrator(orchestrator, test_queue)

        test_job = create_test_job_fixture("consumer_test_job")
        _ = orchestrator.publish(test_queue, test_job)

        consumer.consume(num_messages=1)

        assert len(consumer.processed_jobs) == 1
        processed_job = consumer.processed_jobs[0]
        assert isinstance(processed_job, dict)
        assert processed_job["id"] == test_job.id
        assert processed_job["payload"]["data"] == "test_input"

    def test_consumer_error_handling(self, temp_local_client, sample_job_input, sample_job_output, create_test_job_fixture):
        """Test consumer error handling with failing jobs."""

        orchestrator = Orchestrator(backend=temp_local_client)
        test_schema = JobSchema(name="test-consumer-jobs", input_schema=sample_job_input, output_schema=sample_job_output)
        test_queue = orchestrator.register(test_schema)

        class ErrorProneWorker(Consumer):
            def __init__(self, name):
                super().__init__()
                self.processed_jobs = []
                self.errors = []

            def run(self, job_dict):
                payload = job_dict.get("payload", {})
                if payload.get("data") == "fail_me":
                    raise Exception("Simulated processing error")

                self.processed_jobs.append(job_dict)
                return {"result": "success"}

        consumer = ErrorProneWorker("test_consumer_jobs")
        consumer.connect_to_orchestrator(orchestrator, test_queue)

        success_job = create_test_job_fixture("success_job")
        fail_job = create_test_job_fixture("fail_job", input_data_str="fail_me")

        orchestrator.publish(test_queue, success_job)
        orchestrator.publish(test_queue, fail_job)

        consumer.consume(num_messages=2)

        assert len(consumer.processed_jobs) == 1
        assert consumer.processed_jobs[0]["id"] == success_job.id

        remaining = orchestrator.count_queue_messages(test_queue)
        assert remaining == 0

    def test_consumer_multi_queue(self, temp_local_client, sample_job_input, sample_job_output, create_test_job_fixture):
        """Test consumer consuming from multiple queues."""
        orchestrator = Orchestrator(backend=temp_local_client)
        schema1 = JobSchema(name="test-consumer-jobs:1", input_schema=sample_job_input, output_schema=sample_job_output)
        schema2 = JobSchema(name="test-consumer-jobs:2", input_schema=sample_job_input, output_schema=sample_job_output)
        queue1 = orchestrator.register(schema1)
        queue2 = orchestrator.register(schema2)

        class MultiQueueWorker(Consumer):
            def __init__(self, name):
                super().__init__()
                self.processed_jobs = []

            def run(self, job_dict):
                self.processed_jobs.append(job_dict)
                return {"result": "multi_queue_processed"}

        consumer = MultiQueueWorker("test_consumer_jobs")
        consumer.connect_to_orchestrator(orchestrator, queue1)

        job1 = create_test_job_fixture("queue1_job")
        job2 = create_test_job_fixture("queue2_job")

        orchestrator.publish(queue1, job1)
        orchestrator.publish(queue2, job2)

        consumer.consume(num_messages=2, queues=[queue1, queue2])

        assert len(consumer.processed_jobs) == 2
        processed_names = [job["name"] for job in consumer.processed_jobs]
        assert "queue1_job" in processed_names
        assert "queue2_job" in processed_names

    def test_consumer_consume_until_empty(self, temp_local_client, sample_job_input, sample_job_output, create_test_job_fixture):
        """Test consume_until_empty functionality."""

        orchestrator = Orchestrator(backend=temp_local_client)
        test_schema = JobSchema(name="test-consumer-jobs", input_schema=sample_job_input, output_schema=sample_job_output)
        test_queue = orchestrator.register(test_schema)

        class EmptyTestWorker(Consumer):
            def __init__(self, name):
                super().__init__()
                self.processed_count = 0

            def run(self, job_dict):
                self.processed_count += 1
                return {"result": f"processed_{self.processed_count}"}

        consumer = EmptyTestWorker("test_consumer_jobs")
        consumer.connect_to_orchestrator(orchestrator, test_queue)

        job_count = 5
        for i in range(job_count):
            job = create_test_job_fixture(f"empty_test_job_{i}")
            orchestrator.publish(test_queue, job)

        consumer.consume_until_empty()

        assert consumer.processed_count == job_count

        remaining = orchestrator.count_queue_messages(test_queue)
        assert remaining == 0

    def test_consumer_dict_message_structure(self, temp_local_client, sample_job_input, sample_job_output, create_test_job_fixture):
        """Test that consumers receive properly structured dict messages."""

        orchestrator = Orchestrator(backend=temp_local_client)
        test_schema = JobSchema(name="test-consumer-jobs", input_schema=sample_job_input, output_schema=sample_job_output)
        test_queue = orchestrator.register(test_schema)

        class StructureTestWorker(Consumer):
            def __init__(self, name):
                super().__init__()
                self.received_message = None

            def run(self, job_dict):
                self.received_message = job_dict

                assert isinstance(job_dict, dict)

                required_fields = ["id", "name", "schema_name", "payload"]
                for field in required_fields:
                    assert field in job_dict, f"Missing required field: {field}"

                assert isinstance(job_dict["payload"], dict)
                assert "data" in job_dict["payload"]
                assert "param1" in job_dict["payload"]

                return {"result": "structure_verified"}

        consumer = StructureTestWorker("test_consumer_jobs")
        consumer.connect_to_orchestrator(orchestrator, test_queue)

        test_job = create_test_job_fixture("structure_test_job")
        orchestrator.publish(test_queue, test_job)

        consumer.consume(num_messages=1)

        assert consumer.received_message is not None
        assert consumer.received_message["payload"]["data"] == "test_input"
        assert consumer.received_message["payload"]["param1"] == "value1"

    def test_consumer_not_connected_consume(self):
        """Test calling consume before connecting."""

        class DisconnectedWorker(Consumer):
            def run(self, job_dict):
                return {"result": "processed"}

        consumer = DisconnectedWorker()

        with pytest.raises(RuntimeError, match="Consumer not connected. Call connect\\(\\) first"):
            consumer.consume(num_messages=1)

    def test_consumer_not_connected_consume_until_empty(self):
        """Test calling consume_until_empty before connecting."""

        class DisconnectedWorker(Consumer):
            def run(self, job_dict):
                return {"result": "processed"}

        consumer = DisconnectedWorker()

        with pytest.raises(RuntimeError, match="Consumer not connected. Call connect\\(\\) first"):
            consumer.consume_until_empty()

    def test_abstract_run_method(self):
        """Test that Consumer is abstract and run method must be implemented."""
        consumer = Consumer()

        result = consumer.run({"test": "data"})
        assert result is None  # The base implementation just passes, returns None

        assert hasattr(consumer.run, "__isabstractmethod__")

        class ConcreteWorker(Consumer):
            def run(self, job_dict):
                return {"result": "concrete_implementation"}

        concrete_consumer = ConcreteWorker()
        result = concrete_consumer.run({"test": "data"})
        assert result["result"] == "concrete_implementation"

    def test_double_connect_raises(self, temp_local_client, sample_job_input, sample_job_output):
        """Ensure connect raises RuntimeError if called twice on same Consumer."""

        orchestrator = Orchestrator(backend=temp_local_client)
        test_schema = JobSchema(name="test-consumer-jobs", input_schema=sample_job_input, output_schema=sample_job_output)
        test_queue = orchestrator.register(test_schema)

        class DummyWorker(Consumer):
            def run(self, job_dict):
                return {}

        dummy = DummyWorker()
        dummy.connect_to_orchestrator(orchestrator, test_queue)
        with pytest.raises(RuntimeError):
            dummy.connect_to_orchestrator(orchestrator, test_queue)

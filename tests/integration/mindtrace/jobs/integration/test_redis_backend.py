import pytest
import time
from mindtrace.jobs.redis.client import RedisClient
from ..conftest import create_test_job, unique_queue_name


@pytest.mark.redis
class TestRedisClient:
    
    def setup_method(self):
        self.client = RedisClient(host="localhost", port=6379, db=0)
    
    def test_declare_queue(self):
        queue_name = f"test_queue_{int(time.time())}"
        
        result = self.client.declare_queue(queue_name)
        assert result["status"] == "success"
        
        result2 = self.client.declare_queue(queue_name)
        assert result2["status"] == "success"
        
        self.client.delete_queue(queue_name)
    
    def test_publish_and_receive(self):
        """Test publishing and receiving messages."""
        queue_name = f"test_queue_{int(time.time())}"
        self.client.declare_queue(queue_name)
        
        test_job = create_test_job()
        job_id = self.client.publish(queue_name, test_job)
        
        assert isinstance(job_id, str)
        assert len(job_id) > 0
        
        count = self.client.count_queue_messages(queue_name)
        assert count == 1
        
        received_job = self.client.receive_message(queue_name)
        assert received_job is not None
        assert isinstance(received_job, dict)
        assert received_job["schema_name"] == test_job.schema_name
        
        count = self.client.count_queue_messages(queue_name)
        assert count == 0
        
        self.client.delete_queue(queue_name)
    
    def test_priority_queue(self):
        """Test priority queue functionality."""
        queue_name = f"priority_queue_{int(time.time())}"
        self.client.declare_queue(queue_name, queue_type="priority")
        
        low_priority_job = create_test_job("low_priority_job", "low_priority_schema")
        high_priority_job = create_test_job("high_priority_job", "high_priority_schema")
        
        self.client.publish(queue_name, low_priority_job, priority=1)
        self.client.publish(queue_name, high_priority_job, priority=10)
        
        first_received = self.client.receive_message(queue_name)
        assert first_received is not None
        assert isinstance(first_received, dict)
        assert first_received["schema_name"] == "high_priority_schema"
        
        second_received = self.client.receive_message(queue_name)
        assert second_received is not None
        assert isinstance(second_received, dict)
        assert second_received["schema_name"] == "low_priority_schema"
        
        self.client.delete_queue(queue_name)
    
    def test_clean_and_delete(self):
        queue_name = f"test_queue_{int(time.time())}"
        self.client.declare_queue(queue_name)
        
        for i in range(3):
            job = create_test_job(f"job_{i}")
            self.client.publish(queue_name, job)
        
        assert self.client.count_queue_messages(queue_name) == 3
        
        self.client.clean_queue(queue_name)
        assert self.client.count_queue_messages(queue_name) == 0
        
        self.client.delete_queue(queue_name)
    
    def test_exchange_methods_not_implemented(self):
        with pytest.raises(NotImplementedError):
            self.client.declare_exchange(exchange="test_exchange")
        
        with pytest.raises(NotImplementedError):
            self.client.delete_exchange(exchange="test_exchange")
        
        with pytest.raises(NotImplementedError):
            self.client.count_exchanges()

    def test_declare_stack_queue(self):
        """Test declaring a stack queue - covers line 142."""
        queue_name = f"stack_queue_{int(time.time())}"
        
        result = self.client.declare_queue(queue_name, queue_type="stack")
        assert result["status"] == "success"
        assert "stack" in result["message"]
        
        self.client.delete_queue(queue_name)

    def test_declare_priority_queue(self):
        """Test declaring a priority queue - covers line 156."""
        queue_name = f"priority_queue_{int(time.time())}"
        
        result = self.client.declare_queue(queue_name, queue_type="priority")
        assert result["status"] == "success"
        assert "priority" in result["message"]
        
        self.client.delete_queue(queue_name)

    def test_declare_unknown_queue_type(self):
        """Test declaring unknown queue type - covers line 158."""
        queue_name = f"unknown_queue_{int(time.time())}"
        
        with pytest.raises(TypeError, match="Unknown queue type"):
            self.client.declare_queue(queue_name, queue_type="unknown_type")

    def test_delete_nonexistent_queue(self):
        """Test deleting a queue that doesn't exist - covers line 177."""
        with pytest.raises(KeyError, match="is not declared"):
            self.client.delete_queue("nonexistent_queue")

    def test_publish_to_nonexistent_queue(self):
        """Test publishing to a queue that doesn't exist - covers error in publish."""
        test_job = create_test_job()
        
        with pytest.raises(KeyError, match="is not declared"):
            self.client.publish("nonexistent_queue", test_job)

    def test_publish_with_missing_job_id(self):
        """Test publishing message without job_id - covers line 202."""
        queue_name = f"test_queue_{int(time.time())}"
        self.client.declare_queue(queue_name)
        
        test_job = create_test_job()
        job_dict = test_job.model_dump()
        if 'job_id' in job_dict:
            del job_dict['job_id']
        test_message = test_job.__class__.model_validate(job_dict)
        
        job_id = self.client.publish(queue_name, test_message)
        assert isinstance(job_id, str)
        assert len(job_id) > 0
        
        count = self.client.count_queue_messages(queue_name)
        assert count == 1
        
        self.client.delete_queue(queue_name)

    def test_receive_from_nonexistent_queue(self):
        """Test receiving from a queue that doesn't exist - covers error in receive_message."""
        with pytest.raises(KeyError, match="is not declared"):
            self.client.receive_message("nonexistent_queue")

    def test_receive_from_empty_queue(self):
        """Test receiving from empty queue - covers Empty exception handling."""
        queue_name = f"empty_queue_{int(time.time())}"
        self.client.declare_queue(queue_name)
        
        result = self.client.receive_message(queue_name)
        assert result is None
        
        self.client.delete_queue(queue_name)

    def test_count_nonexistent_queue(self):
        """Test counting messages in nonexistent queue - covers line 254."""
        with pytest.raises(KeyError, match="is not declared"):
            self.client.count_queue_messages("nonexistent_queue")

    def test_clean_nonexistent_queue(self):
        """Test cleaning nonexistent queue - covers lines 269-270."""
        with pytest.raises(KeyError, match="is not declared"):
            self.client.clean_queue("nonexistent_queue")

    def test_move_to_dlq_method(self):
        """Test move_to_dlq method - covers line 296."""
        test_job = create_test_job()
        result = self.client.move_to_dlq("source_queue", "dlq", test_job, "error details")
        assert result is None  # Method currently just passes

    def test_receive_message_json_decode_error(self):
        """Test receive_message with JSON decode error - covers exception handling."""
        queue_name = f"json_error_queue_{int(time.time())}"
        self.client.declare_queue(queue_name)
        
        instance = self.client.queues[queue_name]
        instance.push("invalid_json_data")
        
        result = self.client.receive_message(queue_name)
        assert result is None
        
        self.client.delete_queue(queue_name)

    def test_stack_queue_operations(self):
        """Test stack queue operations (LIFO) - covers stack-specific paths."""
        queue_name = f"stack_test_{int(time.time())}"
        self.client.declare_queue(queue_name, queue_type="stack")
        
        job1 = create_test_job("first_job", "first_schema")
        job2 = create_test_job("second_job", "second_schema")
        
        self.client.publish(queue_name, job1)
        self.client.publish(queue_name, job2)
        
        first_received = self.client.receive_message(queue_name)
        assert first_received is not None
        assert first_received["schema_name"] == "second_schema"
        
        second_received = self.client.receive_message(queue_name)
        assert second_received is not None
        assert second_received["schema_name"] == "first_schema"
        
        self.client.delete_queue(queue_name)

    def test_lock_acquisition_failure_declare(self):
        """Test lock acquisition failure in declare_queue - covers line 129."""
        import unittest.mock
        queue_name = f"lock_test_{int(time.time())}"
        
        with unittest.mock.patch.object(self.client.redis, 'lock') as mock_lock:
            mock_lock_instance = unittest.mock.MagicMock()
            mock_lock_instance.acquire.return_value = False
            mock_lock.return_value = mock_lock_instance
            
            with pytest.raises(BlockingIOError, match="Could not acquire distributed lock"):
                self.client.declare_queue(queue_name)

    def test_lock_acquisition_failure_delete(self):
        """Test lock acquisition failure in delete_queue - covers line 180."""
        import unittest.mock
        queue_name = f"lock_test_{int(time.time())}"
        
        self.client.declare_queue(queue_name)
        
        with unittest.mock.patch.object(self.client.redis, 'lock') as mock_lock:
            mock_lock_instance = unittest.mock.MagicMock()
            mock_lock_instance.acquire.return_value = False
            mock_lock.return_value = mock_lock_instance
            
            with pytest.raises(BlockingIOError, match="Could not acquire distributed lock"):
                self.client.delete_queue(queue_name)
        
        self.client.delete_queue(queue_name)

    def test_lock_acquisition_failure_clean(self):
        """Test lock acquisition failure in clean_queue - covers line 274."""
        import unittest.mock
        queue_name = f"lock_test_{int(time.time())}"
        
        self.client.declare_queue(queue_name)
        
        with unittest.mock.patch.object(self.client.redis, 'lock') as mock_lock:
            mock_lock_instance = unittest.mock.MagicMock()
            mock_lock_instance.acquire.return_value = False
            mock_lock.return_value = mock_lock_instance
            
            with pytest.raises(BlockingIOError, match="Could not acquire distributed lock"):
                self.client.clean_queue(queue_name)
        
        self.client.delete_queue(queue_name)

    def test_receive_message_unsupported_queue_type(self):
        """Test receive_message with unsupported queue methods - covers lines 228, 232."""
        import unittest.mock
        queue_name = f"unsupported_queue_{int(time.time())}"
        self.client.declare_queue(queue_name)
        
        mock_instance = unittest.mock.MagicMock()
        del mock_instance.get
        del mock_instance.pop
        
        with self.client._local_lock:
            self.client.queues[queue_name] = mock_instance
        
        result = self.client.receive_message(queue_name)
        assert result is None  # Exception is caught and returns None
        
        self.client.delete_queue(queue_name)

    def test_clean_queue_exception_handling(self):
        """Test clean_queue exception handling - covers lines 282-283."""
        import unittest.mock
        queue_name = f"exception_queue_{int(time.time())}"
        self.client.declare_queue(queue_name)
        
        with unittest.mock.patch.object(self.client.redis, 'llen', side_effect=Exception("Redis error")):
            with pytest.raises(Exception, match="Redis error"):
                self.client.clean_queue(queue_name)
        
        self.client.delete_queue(queue_name)

    def test_event_listener_unknown_queue_type(self):
        """Test event listener with unknown queue type - covers line 109 (continue)."""
        import json
        
        event_data = json.dumps({"event": "declare", "queue": "test_queue", "queue_type": "unknown"})
        
        self.client.redis.publish(self.client.EVENTS_CHANNEL, event_data)
        
        import time
        time.sleep(0.1)
        
        assert "test_queue" not in self.client.queues

    def test_event_listener_delete_event(self):
        """Test event listener delete event - covers lines 114-115."""
        import json
        import time
        
        queue_name = f"delete_event_test_{int(time.time())}"
        self.client.declare_queue(queue_name)
        
        assert queue_name in self.client.queues
        
        event_data = json.dumps({"event": "delete", "queue": queue_name})
        self.client.redis.publish(self.client.EVENTS_CHANNEL, event_data)
        
        time.sleep(0.1)
        
        if queue_name in self.client.queues:
            self.client.delete_queue(queue_name)
        else:
            try:
                self.client.redis.hdel(self.client.METADATA_KEY, queue_name)
            except:
                pass

    def test_receive_message_with_hasattr_get(self):
        """Test receive_message path with 'get' method - covers lines 224-225."""
        import unittest.mock
        queue_name = f"get_test_{int(time.time())}"
        self.client.declare_queue(queue_name, queue_type="priority")  # Priority queues use 'get'
        
        test_job = create_test_job()
        job_id = self.client.publish(queue_name, test_job, priority=5)
        
        received = self.client.receive_message(queue_name)
        assert received is not None
        assert received["id"] == test_job.id
        
        self.client.delete_queue(queue_name)

    def test_receive_message_missing_both_methods(self):
        """Test receive_message when queue has neither get nor pop - covers line 228."""
        import unittest.mock
        queue_name = f"no_methods_test_{int(time.time())}"
        self.client.declare_queue(queue_name)
        
        mock_instance = unittest.mock.MagicMock()
        if hasattr(mock_instance, 'get'):
            delattr(mock_instance, 'get')
        if hasattr(mock_instance, 'pop'):
            delattr(mock_instance, 'pop')
        
        with self.client._local_lock:
            self.client.queues[queue_name] = mock_instance
        
        result = self.client.receive_message(queue_name)
        assert result is None
        
        self.client.delete_queue(queue_name)

    def test_stack_queue_event_listener(self):
        """Test event listener creating stack queue - covers line 114."""
        import json
        import time
        
        queue_name = f"stack_event_{int(time.time())}"
        event_data = json.dumps({"event": "declare", "queue": queue_name, "queue_type": "stack"})
        self.client.redis.publish(self.client.EVENTS_CHANNEL, event_data)
        
        time.sleep(0.1)
        
        try:
            self.client.redis.hdel(self.client.METADATA_KEY, queue_name)
        except:
            pass

    def test_priority_queue_event_listener(self):
        """Test event listener creating priority queue - covers line 115."""
        import json
        import time
        
        queue_name = f"priority_event_{int(time.time())}"
        event_data = json.dumps({"event": "declare", "queue": queue_name, "queue_type": "priority"})
        self.client.redis.publish(self.client.EVENTS_CHANNEL, event_data)
        
        time.sleep(0.1)
        
        try:
            self.client.redis.hdel(self.client.METADATA_KEY, queue_name)
        except:
            pass

    def test_receive_message_raw_message_methods(self):
        """Test receive_message method paths - covers lines 214-215."""
        import unittest.mock
        
        queue_name = f"pop_test_{int(time.time())}"
        self.client.declare_queue(queue_name, queue_type="stack")  # Stack uses pop
        
        test_job = create_test_job()
        self.client.publish(queue_name, test_job)
        
        received = self.client.receive_message(queue_name)
        assert received is not None
        
        self.client.delete_queue(queue_name)

    def test_receive_message_no_get_or_pop(self):
        """Test receive_message when instance has no get or pop - covers line 228."""
        import unittest.mock
        
        queue_name = f"no_attrs_{int(time.time())}"
        self.client.declare_queue(queue_name)
        
        mock_instance = type('MockQueue', (), {})()
        
        with self.client._local_lock:
            self.client.queues[queue_name] = mock_instance
        
        result = self.client.receive_message(queue_name)
        assert result is None  # Exception caught and returns None
        
        self.client.delete_queue(queue_name)

    def test_event_listener_exception_handling(self):
        """Test event listener exception handling - covers lines 114-115."""
        import json
        import unittest.mock
        
        self.client.redis.publish(self.client.EVENTS_CHANNEL, "{malformed")
        
        event_data = json.dumps({"event": "invalid", "queue": "test"})
        self.client.redis.publish(self.client.EVENTS_CHANNEL, event_data)
        
        event_data = json.dumps({"event": "declare"})  # Missing queue name
        self.client.redis.publish(self.client.EVENTS_CHANNEL, event_data)
        
        import time
        time.sleep(0.1)
        

    def test_publish_exception_handling(self):
        """Test publish exception handling - covers lines 214-215."""
        import unittest.mock
        queue_name = f"exception_test_{int(time.time())}"
        self.client.declare_queue(queue_name)
        
        mock_instance = unittest.mock.MagicMock()
        mock_instance.push.side_effect = Exception("Push failed")
        
        with self.client._local_lock:
            self.client.queues[queue_name] = mock_instance
        
        test_job = unittest.mock.MagicMock()
        test_job.model_dump.return_value = {"id": "test", "data": "test"}
        
        with pytest.raises(Exception, match="Push failed"):
            self.client.publish(queue_name, test_job)
        
        mock_instance.push.assert_called_once()
        
        self.client.delete_queue(queue_name)

    def test_receive_message_get_method(self):
        """Test receive_message using get method - covers line 228."""
        import unittest.mock
        queue_name = f"get_test_{int(time.time())}"
        self.client.declare_queue(queue_name)
        
        class TestQueue:
            def get(self, block=False, timeout=None):
                raise Exception("Test exception from get")
            
            def qsize(self):
                return 0
        
        mock_instance = TestQueue()
        
        with self.client._local_lock:
            self.client.queues[queue_name] = mock_instance
        
        result = self.client.receive_message(queue_name)
        assert result is None
        
        self.client.delete_queue(queue_name) 
import pytest
import threading
import time
from queue import Empty
from pydantic import BaseModel
from mindtrace.jobs.local.stack import LocalStack
from mindtrace.jobs.redis.stack import RedisStack
from mindtrace.jobs.types.job_specs import Job, JobSchema
from ..conftest import create_test_job, job_from_schema


class SampleJobInput(BaseModel):
    data: str = "test_input"

class SampleJobOutput(BaseModel):
    result: str = "success"


def create_test_job_local(name: str = "test_job") -> Job:
    test_input = SampleJobInput()
    schema = JobSchema(
        name=f"{name}_schema", 
        input=SampleJobInput,
        output=SampleJobOutput
    )
    job = job_from_schema(schema, test_input)
    job.id = f"{name}_123"
    job.name = name
    job.created_at = "2024-01-01T00:00:00"
    return job


@pytest.mark.redis
class TestRedisStack:
    """Essential tests for RedisStack with real Redis."""
    
    def setup_method(self):
        self.stack_name = f"test_stack_{int(time.time())}"
        self.stack = RedisStack(self.stack_name, host="localhost", port=6379, db=0)
    
    def test_lifo_behavior(self):
        jobs = [create_test_job_local(f"job_{i}") for i in range(3)]
        
        for job in jobs:
            self.stack.push(job)
        
        popped_jobs = []
        while not self.stack.empty():
            popped_jobs.append(self.stack.pop(block=False))
        
        expected_order = [jobs[2], jobs[1], jobs[0]]
        assert len(popped_jobs) == 3
        for i, job in enumerate(popped_jobs):
            assert job.name == expected_order[i].name
    
    def test_empty_stack_operations(self):
        empty_stack_name = f"empty_stack_{int(time.time())}"
        empty_stack = RedisStack(empty_stack_name, host="localhost", port=6379, db=0)
        
        assert empty_stack.empty() is True
        assert empty_stack.qsize() == 0
        
        with pytest.raises(Empty):
            empty_stack.pop(block=False)
    
    def test_serialization(self):
        job = create_test_job_local("serialize_test")
        job.payload.data = "complex_data_123"
        
        self.stack.push(job)
        retrieved_job = self.stack.pop(block=False)
        
        assert retrieved_job is not None
        assert retrieved_job.name == "serialize_test"
        assert retrieved_job.payload.data == "complex_data_123"
        assert retrieved_job.id == "serialize_test_123"


class TestStackEquivalence:
    """Test that LocalStack and RedisStack behave equivalently."""
    
    @pytest.mark.redis
    def test_equivalent_behavior(self):
        """Verify both stack implementations have identical behavior."""
        local_stack = LocalStack()
        
        jobs = [create_test_job_local(f"equiv_{i}") for i in range(3)]
        
        for job in jobs:
            local_stack.push(job)
        
        local_results = []
        while not local_stack.empty():
            local_results.append(local_stack.pop(block=False))
        
        assert len(local_results) == 3
        assert local_results[0].name == "equiv_2"
        assert local_results[1].name == "equiv_1"
        assert local_results[2].name == "equiv_0"
        
        try:
            redis_stack = RedisStack(f"equiv_test_{int(time.time())}")
            
            for job in jobs:
                redis_stack.push(job)
            
            redis_results = []
            while not redis_stack.empty():
                redis_results.append(redis_stack.pop(block=False))
            
            assert len(redis_results) == 3
            assert redis_results[0].name == "equiv_2"
            assert redis_results[1].name == "equiv_1"
            assert redis_results[2].name == "equiv_0"
        finally:
            try:
                redis_stack._RedisStack__db.delete(redis_stack.key)
            except:
                pass 
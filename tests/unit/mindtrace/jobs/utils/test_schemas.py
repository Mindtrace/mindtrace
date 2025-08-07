from datetime import datetime
from unittest.mock import patch, MagicMock
from uuid import uuid4

import pytest
from pydantic import BaseModel, ValidationError

from mindtrace.jobs.utils.schemas import job_from_schema
from mindtrace.jobs.types.job_specs import Job, JobSchema


class MockInputSchema(BaseModel):
    """Mock input schema for testing."""
    data: str
    count: int = 0


class MockOutputSchema(BaseModel):
    """Mock output schema for testing."""
    result: str


class MockJobSchema(JobSchema):
    """Mock job schema for testing."""
    name: str = "test-job"
    input_schema: type[BaseModel] = MockInputSchema
    output_schema: type[BaseModel] = MockOutputSchema


class TestJobFromSchema:
    """Tests for the job_from_schema function."""

    def test_job_from_schema_with_valid_input_object(self):
        """Test creating a job with a valid input schema object."""
        schema = MockJobSchema()
        input_data = MockInputSchema(data="test-data", count=5)
        
        with patch('mindtrace.jobs.utils.schemas.uuid.uuid4') as mock_uuid:
            mock_uuid.return_value = uuid4()
            with patch('mindtrace.jobs.utils.schemas.datetime') as mock_datetime:
                mock_datetime.now.return_value = datetime(2023, 1, 1, 12, 0, 0)
                
                result = job_from_schema(schema, input_data)
                
                assert isinstance(result, Job)
                assert result.id == str(mock_uuid.return_value)
                assert result.name == "test-job"
                assert result.schema_name == "test-job"
                assert result.payload == input_data
                assert result.created_at == "2023-01-01T12:00:00"

    def test_job_from_schema_with_dictionary_input(self):
        """Test creating a job with dictionary input data."""
        schema = MockJobSchema()
        input_data = {"data": "test-data", "count": 10}
        
        with patch('mindtrace.jobs.utils.schemas.uuid.uuid4') as mock_uuid:
            mock_uuid.return_value = uuid4()
            with patch('mindtrace.jobs.utils.schemas.datetime') as mock_datetime:
                mock_datetime.now.return_value = datetime(2023, 1, 1, 12, 0, 0)
                
                result = job_from_schema(schema, input_data)
                
                assert isinstance(result, Job)
                assert result.id == str(mock_uuid.return_value)
                assert result.name == "test-job"
                assert result.schema_name == "test-job"
                assert isinstance(result.payload, MockInputSchema)
                assert result.payload.data == "test-data"
                assert result.payload.count == 10
                assert result.created_at == "2023-01-01T12:00:00"

    def test_job_from_schema_with_partial_dictionary_input(self):
        """Test creating a job with partial dictionary input (using defaults)."""
        schema = MockJobSchema()
        input_data = {"data": "test-data"}  # count will use default value
        
        with patch('mindtrace.jobs.utils.schemas.uuid.uuid4') as mock_uuid:
            mock_uuid.return_value = uuid4()
            with patch('mindtrace.jobs.utils.schemas.datetime') as mock_datetime:
                mock_datetime.now.return_value = datetime(2023, 1, 1, 12, 0, 0)
                
                result = job_from_schema(schema, input_data)
                
                assert isinstance(result, Job)
                assert result.payload.data == "test-data"
                assert result.payload.count == 0  # default value

    def test_job_from_schema_with_different_schema_name(self):
        """Test creating a job with a schema that has a different name."""
        schema = MockJobSchema()
        schema.name = "different-job-name"
        input_data = MockInputSchema(data="test-data")
        
        with patch('mindtrace.jobs.utils.schemas.uuid.uuid4') as mock_uuid:
            mock_uuid.return_value = uuid4()
            with patch('mindtrace.jobs.utils.schemas.datetime') as mock_datetime:
                mock_datetime.now.return_value = datetime(2023, 1, 1, 12, 0, 0)
                
                result = job_from_schema(schema, input_data)
                
                assert result.name == "different-job-name"
                assert result.schema_name == "different-job-name"

    def test_job_from_schema_validation_error(self):
        """Test that validation errors are raised for invalid input data."""
        schema = MockJobSchema()
        input_data = {"invalid_field": "test-data"}  # Missing required 'data' field
        
        with pytest.raises(ValidationError):
            job_from_schema(schema, input_data)

    def test_job_from_schema_with_complex_input_schema(self):
        """Test creating a job with a more complex input schema."""
        class ComplexInputSchema(BaseModel):
            name: str
            age: int
            tags: list[str] = []
            metadata: dict = {}
        
        class ComplexJobSchema(JobSchema):
            name: str = "complex-job"
            input_schema: type[BaseModel] = ComplexInputSchema
            output_schema: type[BaseModel] = MockOutputSchema
        
        schema = ComplexJobSchema()
        input_data = {
            "name": "John Doe",
            "age": 30,
            "tags": ["tag1", "tag2"],
            "metadata": {"key": "value"}
        }
        
        with patch('mindtrace.jobs.utils.schemas.uuid.uuid4') as mock_uuid:
            mock_uuid.return_value = uuid4()
            with patch('mindtrace.jobs.utils.schemas.datetime') as mock_datetime:
                mock_datetime.now.return_value = datetime(2023, 1, 1, 12, 0, 0)
                
                result = job_from_schema(schema, input_data)
                
                assert isinstance(result, Job)
                assert result.name == "complex-job"
                assert result.schema_name == "complex-job"
                assert isinstance(result.payload, ComplexInputSchema)
                assert result.payload.name == "John Doe"
                assert result.payload.age == 30
                assert result.payload.tags == ["tag1", "tag2"]
                assert result.payload.metadata == {"key": "value"}

    def test_job_from_schema_with_empty_input_data(self):
        """Test creating a job with empty input data (should raise validation error)."""
        schema = MockJobSchema()
        input_data = {}  # Empty dictionary - missing required 'data' field
        
        with pytest.raises(ValidationError):
            job_from_schema(schema, input_data)

    def test_job_from_schema_with_none_input_data(self):
        """Test creating a job with None input data (should raise TypeError)."""
        schema = MockJobSchema()
        input_data = None
        
        with pytest.raises(TypeError):
            job_from_schema(schema, input_data)

    def test_job_from_schema_with_wrong_input_object_type(self):
        """Test creating a job with wrong input object type."""
        schema = MockJobSchema()
        input_data = MockOutputSchema(result="wrong-type")  # Wrong schema type
        
        with pytest.raises(TypeError):
            job_from_schema(schema, input_data)

    def test_job_from_schema_uuid_generation(self):
        """Test that each job gets a unique UUID."""
        schema = MockJobSchema()
        input_data = MockInputSchema(data="test-data")
        
        with patch('mindtrace.jobs.utils.schemas.datetime') as mock_datetime:
            mock_datetime.now.return_value = datetime(2023, 1, 1, 12, 0, 0)
            
            job1 = job_from_schema(schema, input_data)
            job2 = job_from_schema(schema, input_data)
            
            assert job1.id != job2.id
            assert isinstance(job1.id, str)
            assert isinstance(job2.id, str)

    def test_job_from_schema_timestamp_format(self):
        """Test that the created_at timestamp is in ISO format."""
        schema = MockJobSchema()
        input_data = MockInputSchema(data="test-data")
        
        with patch('mindtrace.jobs.utils.schemas.uuid.uuid4') as mock_uuid:
            mock_uuid.return_value = uuid4()
            with patch('mindtrace.jobs.utils.schemas.datetime') as mock_datetime:
                mock_datetime.now.return_value = datetime(2023, 1, 1, 12, 30, 45, 123456)
                
                result = job_from_schema(schema, input_data)
                
                assert result.created_at == "2023-01-01T12:30:45.123456"

    def test_job_from_schema_payload_immutability(self):
        """Test that the payload is properly set and not modified."""
        schema = MockJobSchema()
        input_data = MockInputSchema(data="test-data", count=5)
        
        with patch('mindtrace.jobs.utils.schemas.uuid.uuid4') as mock_uuid:
            mock_uuid.return_value = uuid4()
            with patch('mindtrace.jobs.utils.schemas.datetime') as mock_datetime:
                mock_datetime.now.return_value = datetime(2023, 1, 1, 12, 0, 0)
                
                result = job_from_schema(schema, input_data)
                
                # Verify payload is the same object
                assert result.payload is input_data
                assert result.payload.data == "test-data"
                assert result.payload.count == 5

    def test_job_from_schema_with_required_fields_only(self):
        """Test creating a job with a schema that has only required fields."""
        class RequiredOnlySchema(BaseModel):
            required_field: str
        
        class RequiredOnlyJobSchema(JobSchema):
            name: str = "required-only-job"
            input_schema: type[BaseModel] = RequiredOnlySchema
            output_schema: type[BaseModel] = MockOutputSchema
        
        schema = RequiredOnlyJobSchema()
        input_data = {"required_field": "test-value"}
        
        with patch('mindtrace.jobs.utils.schemas.uuid.uuid4') as mock_uuid:
            mock_uuid.return_value = uuid4()
            with patch('mindtrace.jobs.utils.schemas.datetime') as mock_datetime:
                mock_datetime.now.return_value = datetime(2023, 1, 1, 12, 0, 0)
                
                result = job_from_schema(schema, input_data)
                
                assert isinstance(result, Job)
                assert result.name == "required-only-job"
                assert isinstance(result.payload, RequiredOnlySchema)
                assert result.payload.required_field == "test-value"

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

import pytest

from mindtrace.cluster.workers.standard_worker_launcher import StandardWorkerLauncher, ProxyWorker
from mindtrace.services import ConnectionManager


class TestProxyWorker:
    """Test ProxyWorker class."""
    
    def test_proxy_worker_creation(self):
        """Test ProxyWorker creation with valid parameters."""
        worker = ProxyWorker(
            worker_type="test.worker.TestWorker",
            worker_params={"param1": "value1", "param2": 42}
        )
        
        assert worker.worker_type == "test.worker.TestWorker"
        assert worker.worker_params == {"param1": "value1", "param2": 42}
    
    def test_proxy_worker_model_dump(self):
        """Test ProxyWorker model_dump method."""
        worker = ProxyWorker(
            worker_type="test.worker.TestWorker",
            worker_params={"param1": "value1"}
        )
        
        result = worker.model_dump()
        
        expected = {
            "worker_type": "test.worker.TestWorker",
            "worker_params": {"param1": "value1"}
        }
        assert result == expected


class TestStandardWorkerLauncher:
    """Test StandardWorkerLauncher class."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir
    
    @pytest.fixture
    def launcher(self, temp_dir):
        """Create a StandardWorkerLauncher instance."""
        return StandardWorkerLauncher(uri=temp_dir)
    
    @pytest.fixture
    def sample_worker(self):
        """Create a sample ProxyWorker for testing."""
        return ProxyWorker(
            worker_type="test.worker.TestWorker",
            worker_params={"param1": "value1", "param2": 42}
        )
    
    def test_launcher_initialization(self, temp_dir):
        """Test StandardWorkerLauncher initialization."""
        launcher = StandardWorkerLauncher(uri=temp_dir)
        assert launcher.uri == temp_dir
    
    def test_save_worker(self, launcher, sample_worker):
        """Test save method."""
        worker_file_path = Path(launcher.uri) / "worker.json"
        
        # Save the worker
        launcher.save(sample_worker)
        
        # Verify file was created
        assert worker_file_path.exists()
        
        # Verify file contents
        with open(worker_file_path, 'r') as f:
            saved_data = json.load(f)
        
        expected_data = {
            "worker_type": "test.worker.TestWorker",
            "worker_params": {"param1": "value1", "param2": 42}
        }
        assert saved_data == expected_data
    
    def test_save_worker_with_file_io_error(self, launcher, sample_worker):
        """Test save method with file I/O error."""
        # Mock open to raise an exception
        with patch('builtins.open', side_effect=IOError("Permission denied")):
            with pytest.raises(IOError, match="Permission denied"):
                launcher.save(sample_worker)
    
    def test_load_worker(self, launcher, sample_worker):
        """Test load method."""
        # First save a worker
        launcher.save(sample_worker)
        
        # Mock the worker class and its launch method
        mock_worker_class = MagicMock()
        mock_worker_instance = MagicMock()
        mock_worker_instance.url = "http://worker:8080"
        mock_worker_class.launch.return_value = mock_worker_instance
        
        with patch('mindtrace.cluster.workers.standard_worker_launcher.get_class', return_value=mock_worker_class):
            # Load the worker
            result = launcher.load(data_type=None, url="http://worker:8080")
            
            # Verify the worker class was retrieved
            mock_worker_class.launch.assert_called_once_with(
                url="http://worker:8080",
                param1="value1",
                param2=42,
                wait_for_launch=True,
                timeout=60
            )
            
            # Verify the result
            assert result == mock_worker_instance
            assert result.url == "http://worker:8080"
    
    def test_load_worker_with_file_not_found(self, launcher):
        """Test load method when worker.json file doesn't exist."""
        with pytest.raises(FileNotFoundError):
            launcher.load(data_type=None, url="http://worker:8080")
    
    def test_load_worker_with_invalid_json(self, launcher):
        """Test load method with invalid JSON in worker.json."""
        # Create a worker.json file with invalid JSON
        worker_file_path = Path(launcher.uri) / "worker.json"
        with open(worker_file_path, 'w') as f:
            f.write("invalid json content")
        
        with pytest.raises(json.JSONDecodeError):
            launcher.load(data_type=None, url="http://worker:8080")
    
    def test_load_worker_with_missing_worker_type(self, launcher):
        """Test load method when worker.json is missing worker_type."""
        # Create a worker.json file with missing worker_type
        worker_file_path = Path(launcher.uri) / "worker.json"
        with open(worker_file_path, 'w') as f:
            json.dump({"worker_params": {"param1": "value1"}}, f)
        
        with pytest.raises(KeyError, match="worker_type"):
            launcher.load(data_type=None, url="http://worker:8080")
    
    def test_load_worker_with_missing_worker_params(self, launcher):
        """Test load method when worker.json is missing worker_params."""
        # Create a worker.json file with missing worker_params
        worker_file_path = Path(launcher.uri) / "worker.json"
        with open(worker_file_path, 'w') as f:
            json.dump({"worker_type": "mindtrace.cluster.workers.echo_worker.EchoWorker"}, f)
        
        with pytest.raises(KeyError, match="worker_params"):
            launcher.load(data_type=None, url="http://worker:8080")
    
    def test_load_worker_with_class_not_found(self, launcher, sample_worker):
        """Test load method when worker class cannot be found."""
        # First save a worker
        launcher.save(sample_worker)
        
        # Mock get_class to raise an exception
        with patch('mindtrace.cluster.workers.standard_worker_launcher.get_class', side_effect=ImportError("Module not found")):
            with pytest.raises(ImportError, match="Module not found"):
                launcher.load(data_type=None, url="http://worker:8080")
    
    def test_load_worker_with_launch_error(self, launcher, sample_worker):
        """Test load method when worker launch fails."""
        # First save a worker
        launcher.save(sample_worker)
        
        # Mock the worker class to raise an exception during launch
        mock_worker_class = MagicMock()
        mock_worker_class.launch.side_effect = RuntimeError("Launch failed")
        
        with patch('mindtrace.cluster.workers.standard_worker_launcher.get_class', return_value=mock_worker_class):
            with pytest.raises(RuntimeError, match="Launch failed"):
                launcher.load(data_type=None, url="http://worker:8080")
    
    def test_load_worker_with_custom_parameters(self, launcher):
        """Test load method with custom worker parameters."""
        # Create a worker with complex parameters
        complex_worker = ProxyWorker(
            worker_type="test.worker.ComplexWorker",
            worker_params={
                "string_param": "test_string",
                "int_param": 123,
                "float_param": 3.14,
                "bool_param": True,
                "list_param": [1, 2, 3],
                "dict_param": {"nested": "value"}
            }
        )
        
        # Save the worker
        launcher.save(complex_worker)
        
        # Mock the worker class
        mock_worker_class = MagicMock()
        mock_worker_instance = MagicMock()
        mock_worker_instance.url = "http://complex-worker:8080"
        mock_worker_class.launch.return_value = mock_worker_instance
        
        with patch('mindtrace.cluster.workers.standard_worker_launcher.get_class', return_value=mock_worker_class):
            # Load the worker
            result = launcher.load(data_type=None, url="http://complex-worker:8080")
            
            # Verify all parameters were passed correctly
            mock_worker_class.launch.assert_called_once_with(
                url="http://complex-worker:8080",
                string_param="test_string",
                int_param=123,
                float_param=3.14,
                bool_param=True,
                list_param=[1, 2, 3],
                dict_param={"nested": "value"},
                wait_for_launch=True,
                timeout=60
            )
            
            assert result == mock_worker_instance 
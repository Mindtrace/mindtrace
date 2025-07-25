import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mindtrace.cluster.core.cluster import StandardWorkerLauncher
from mindtrace.cluster.core.types import ProxyWorker


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
            "worker_params": {"param1": "value1"},
            "git_repo_url": None,
            "git_branch": None,
            "git_commit": None,
            "git_working_dir": None
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
    
    @pytest.fixture
    def git_worker(self):
        """Create a sample ProxyWorker with git configuration for testing."""
        return ProxyWorker(
            worker_type="test.worker.GitWorker",
            worker_params={"param1": "value1", "param2": 42},
            git_repo_url="https://github.com/test/repo.git",
            git_branch="main",
            git_commit="abc123",
            git_working_dir="/app"
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
            "worker_params": {"param1": "value1", "param2": 42},
            "git_repo_url": None,
            "git_branch": None,
            "git_commit": None,
            "git_working_dir": None
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
        
        with patch('mindtrace.cluster.core.cluster.get_class', return_value=mock_worker_class):
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
        
        with pytest.raises(KeyError, match="git_repo_url"):
            launcher.load(data_type=None, url="http://worker:8080")
    
    def test_load_worker_with_missing_worker_params(self, launcher):
        """Test load method when worker.json is missing worker_params."""
        # Create a worker.json file with missing worker_params
        worker_file_path = Path(launcher.uri) / "worker.json"
        with open(worker_file_path, 'w') as f:
            json.dump({"worker_type": "mindtrace.cluster.workers.echo_worker.EchoWorker"}, f)
        
        with pytest.raises(KeyError, match="git_repo_url"):
            launcher.load(data_type=None, url="http://worker:8080")
    
    def test_load_worker_with_class_not_found(self, launcher, sample_worker):
        """Test load method when worker class cannot be found."""
        # First save a worker
        launcher.save(sample_worker)
        
        # Mock get_class to raise an exception
        with patch('mindtrace.cluster.core.cluster.get_class', side_effect=ImportError("Module not found")):
            with pytest.raises(ImportError, match="Module not found"):
                launcher.load(data_type=None, url="http://worker:8080")
    
    def test_load_worker_with_launch_error(self, launcher, sample_worker):
        """Test load method when worker launch fails."""
        # First save a worker
        launcher.save(sample_worker)
        
        # Mock the worker class to raise an exception during launch
        mock_worker_class = MagicMock()
        mock_worker_class.launch.side_effect = RuntimeError("Launch failed")
        
        with patch('mindtrace.cluster.core.cluster.get_class', return_value=mock_worker_class):
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
        
        with patch('mindtrace.cluster.core.cluster.get_class', return_value=mock_worker_class):
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
    
    def test_load_worker_with_git_environment(self, launcher, git_worker):
        """Test load method with git environment configuration."""
        # Save the git worker
        launcher.save(git_worker)
        
        # Mock the GitEnvironment and related components
        mock_environment = MagicMock()
        mock_environment.setup.return_value = "/tmp/working_dir"
        mock_environment.execute.return_value = 12345  # PID
        
        mock_connection_manager = MagicMock()
        mock_timeout_handler = MagicMock()
        mock_timeout_handler.run.return_value = mock_connection_manager
        
        with patch('mindtrace.cluster.core.cluster.GitEnvironment', return_value=mock_environment) as mock_git_env_class, \
             patch('mindtrace.cluster.core.cluster.Timeout', return_value=mock_timeout_handler), \
             patch('mindtrace.cluster.core.cluster.Worker') as mock_worker_class:
            
            # Load the worker
            result = launcher.load(data_type=None, url="http://git-worker:8080")
            
            # Verify GitEnvironment was created with correct parameters
            mock_git_env_class.assert_called_once_with(
                repo_url="https://github.com/test/repo.git",
                branch="main",
                commit="abc123",
                working_dir="/app"
            )
            
            # Verify environment setup was called
            mock_environment.setup.assert_called_once()
            
            # Verify execute was called with correct launch command
            mock_environment.execute.assert_called_once()
            call_args = mock_environment.execute.call_args[0][0]
            assert call_args[0] == "python"
            assert call_args[1] == "-m"
            assert call_args[2] == "mindtrace.services.core.launcher"
            assert call_args[3] == "-s"
            assert call_args[4] == "test.worker.GitWorker"
            assert call_args[5] == "-w"
            assert call_args[6] == "1"
            assert call_args[7] == "-b"
            assert call_args[8] == "git-worker:8080"  # URL without http://
            assert call_args[9] == "-p"
            assert call_args[11] == "-k"
            assert call_args[12] == "uvicorn.workers.UvicornWorker"
            assert call_args[13] == "--init-params"
            
            # Verify init params were passed correctly
            init_params = json.loads(call_args[14])
            assert init_params["url"] == "http://git-worker:8080"
            assert init_params["param1"] == "value1"
            assert init_params["param2"] == 42
            
            # Verify timeout handler was created correctly
            # Note: The Timeout class is mocked, so we check that run() was called
            mock_timeout_handler.run.assert_called_once_with(
                mock_worker_class.connect, url="http://git-worker:8080"
            )
            
            # Verify the result
            assert result == mock_connection_manager
    
    def test_load_worker_with_git_environment_connection_failure(self, launcher, git_worker):
        """Test load method with git environment when connection fails."""
        # Save the git worker
        launcher.save(git_worker)
        
        # Mock the GitEnvironment and related components
        mock_environment = MagicMock()
        mock_environment.setup.return_value = "/tmp/working_dir"
        mock_environment.execute.return_value = 12345  # PID
        
        mock_timeout_handler = MagicMock()
        mock_timeout_handler.run.side_effect = ConnectionRefusedError("Connection refused")
        
        with patch('mindtrace.cluster.core.cluster.GitEnvironment', return_value=mock_environment) as mock_git_env_class, \
             patch('mindtrace.cluster.core.cluster.Timeout', return_value=mock_timeout_handler), \
             patch('mindtrace.cluster.core.cluster.Worker'):
            
            # Load the worker should raise the connection error
            with pytest.raises(ConnectionRefusedError, match="Connection refused"):
                launcher.load(data_type=None, url="http://git-worker:8080")
    
    def test_load_worker_with_git_environment_timeout_error(self, launcher, git_worker):
        """Test load method with git environment when timeout occurs."""
        # Save the git worker
        launcher.save(git_worker)
        
        # Mock the GitEnvironment and related components
        mock_environment = MagicMock()
        mock_environment.setup.return_value = "/tmp/working_dir"
        mock_environment.execute.return_value = 12345  # PID
        
        mock_timeout_handler = MagicMock()
        mock_timeout_handler.run.side_effect = TimeoutError("Connection timeout")
        
        with patch('mindtrace.cluster.core.cluster.GitEnvironment', return_value=mock_environment) as mock_git_env_class, \
             patch('mindtrace.cluster.core.cluster.Timeout', return_value=mock_timeout_handler), \
             patch('mindtrace.cluster.core.cluster.Worker'):
            
            # Load the worker should raise the timeout error
            with pytest.raises(TimeoutError, match="Connection timeout"):
                launcher.load(data_type=None, url="http://git-worker:8080")
    
    def test_load_worker_with_git_environment_http_exception(self, launcher, git_worker):
        """Test load method with git environment when HTTP exception occurs."""
        # Save the git worker
        launcher.save(git_worker)
        
        # Mock the GitEnvironment and related components
        mock_environment = MagicMock()
        mock_environment.setup.return_value = "/tmp/working_dir"
        mock_environment.execute.return_value = 12345  # PID
        
        mock_timeout_handler = MagicMock()
        mock_timeout_handler.run.side_effect = Exception("HTTP 500 error")
        
        with patch('mindtrace.cluster.core.cluster.GitEnvironment', return_value=mock_environment) as mock_git_env_class, \
             patch('mindtrace.cluster.core.cluster.Timeout', return_value=mock_timeout_handler), \
             patch('mindtrace.cluster.core.cluster.Worker'):
            
            # Load the worker should raise the exception
            with pytest.raises(Exception, match="HTTP 500 error"):
                launcher.load(data_type=None, url="http://git-worker:8080")
    
    def test_load_worker_with_git_environment_environment_setup_failure(self, launcher, git_worker):
        """Test load method with git environment when environment setup fails."""
        # Save the git worker
        launcher.save(git_worker)
        
        # Mock the GitEnvironment to raise an exception during setup
        mock_environment = MagicMock()
        mock_environment.setup.side_effect = RuntimeError("Git setup failed")
        
        with patch('mindtrace.cluster.core.cluster.GitEnvironment', return_value=mock_environment):
            # Load the worker should raise the setup error
            with pytest.raises(RuntimeError, match="Git setup failed"):
                launcher.load(data_type=None, url="http://git-worker:8080")
    
    def test_load_worker_with_git_environment_execute_failure(self, launcher, git_worker):
        """Test load method with git environment when execute fails."""
        # Save the git worker
        launcher.save(git_worker)
        
        # Mock the GitEnvironment to raise an exception during execute
        mock_environment = MagicMock()
        mock_environment.setup.return_value = "/tmp/working_dir"
        mock_environment.execute.side_effect = RuntimeError("Execute failed")
        
        with patch('mindtrace.cluster.core.cluster.GitEnvironment', return_value=mock_environment):
            # Load the worker should raise the execute error
            with pytest.raises(RuntimeError, match="Execute failed"):
                launcher.load(data_type=None, url="http://git-worker:8080")
    
    def test_load_worker_with_git_environment_url_stripping(self, launcher, git_worker):
        """Test load method with git environment and different URL formats."""
        # Save the git worker
        launcher.save(git_worker)
        
        # Mock the GitEnvironment and related components
        mock_environment = MagicMock()
        mock_environment.setup.return_value = "/tmp/working_dir"
        mock_environment.execute.return_value = 12345  # PID
        
        mock_connection_manager = MagicMock()
        mock_timeout_handler = MagicMock()
        mock_timeout_handler.run.return_value = mock_connection_manager
        
        with patch('mindtrace.cluster.core.cluster.GitEnvironment', return_value=mock_environment), \
             patch('mindtrace.cluster.core.cluster.Timeout', return_value=mock_timeout_handler), \
             patch('mindtrace.cluster.core.cluster.Worker'):
            
            # Test with https URL
            launcher.load(data_type=None, url="https://secure-worker:8443")
            
            # Verify the URL was stripped correctly
            call_args = mock_environment.execute.call_args[0][0]
            assert call_args[8] == "secure-worker:8443"  # URL with https:// stripped correctly
    
    def test_load_worker_with_git_environment_complex_parameters(self, launcher):
        """Test load method with git environment and complex worker parameters."""
        # Create a git worker with complex parameters
        complex_git_worker = ProxyWorker(
            worker_type="test.worker.ComplexGitWorker",
            worker_params={
                "string_param": "test_string",
                "int_param": 123,
                "float_param": 3.14,
                "bool_param": True,
                "list_param": [1, 2, 3],
                "dict_param": {"nested": "value"},
                "none_param": None
            },
            git_repo_url="https://github.com/test/complex-repo.git",
            git_branch="develop",
            git_commit="def456",
            git_working_dir="/app/worker"
        )
        
        # Save the git worker
        launcher.save(complex_git_worker)
        
        # Mock the GitEnvironment and related components
        mock_environment = MagicMock()
        mock_environment.setup.return_value = "/tmp/complex_working_dir"
        mock_environment.execute.return_value = 67890  # PID
        
        mock_connection_manager = MagicMock()
        mock_timeout_handler = MagicMock()
        mock_timeout_handler.run.return_value = mock_connection_manager
        
        with patch('mindtrace.cluster.core.cluster.GitEnvironment', return_value=mock_environment), \
             patch('mindtrace.cluster.core.cluster.Timeout', return_value=mock_timeout_handler), \
             patch('mindtrace.cluster.core.cluster.Worker'):
            
            # Load the worker
            result = launcher.load(data_type=None, url="http://complex-git-worker:8080")
            
            # Verify init params were passed correctly
            call_args = mock_environment.execute.call_args[0][0]
            init_params = json.loads(call_args[14])
            assert init_params["url"] == "http://complex-git-worker:8080"
            assert init_params["string_param"] == "test_string"
            assert init_params["int_param"] == 123
            assert init_params["float_param"] == 3.14
            assert init_params["bool_param"] is True
            assert init_params["list_param"] == [1, 2, 3]
            assert init_params["dict_param"] == {"nested": "value"}
            assert init_params["none_param"] is None
            
            # Verify the result
            assert result == mock_connection_manager
    
    def test_load_worker_with_git_environment_none_values(self, launcher):
        """Test load method with git environment when git parameters are None."""
        # Create a git worker with None git parameters
        git_worker_none = ProxyWorker(
            worker_type="test.worker.GitWorkerNone",
            worker_params={"param1": "value1"},
            git_repo_url="https://github.com/test/repo.git",
            git_branch=None,
            git_commit=None,
            git_working_dir=None
        )
        
        # Save the git worker
        launcher.save(git_worker_none)
        
        # Mock the GitEnvironment and related components
        mock_environment = MagicMock()
        mock_environment.setup.return_value = "/tmp/working_dir"
        mock_environment.execute.return_value = 12345  # PID
        
        mock_connection_manager = MagicMock()
        mock_timeout_handler = MagicMock()
        mock_timeout_handler.run.return_value = mock_connection_manager
        
        with patch('mindtrace.cluster.core.cluster.GitEnvironment', return_value=mock_environment) as mock_git_env_class, \
             patch('mindtrace.cluster.core.cluster.Timeout', return_value=mock_timeout_handler), \
             patch('mindtrace.cluster.core.cluster.Worker'):
            
            # Load the worker
            result = launcher.load(data_type=None, url="http://git-worker-none:8080")
            
            # Verify GitEnvironment was created with None values
            mock_git_env_class.assert_called_once_with(
                repo_url="https://github.com/test/repo.git",
                branch=None,
                commit=None,
                working_dir=None
            )
            
            # Verify the result
            assert result == mock_connection_manager 
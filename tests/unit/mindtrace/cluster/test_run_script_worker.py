import os
import pytest
from unittest.mock import Mock, patch, MagicMock

from mindtrace.cluster.workers.run_script_worker import RunScriptWorker, RunScriptWorkerInput, RunScriptWorkerOutput


def create_mock_database():
    mock_database = MagicMock()
    mock_database.insert = MagicMock()
    mock_database.find = MagicMock(return_value=[])
    mock_database.delete = MagicMock()
    mock_database.redis_backend = MagicMock()
    mock_database.redis_backend.model_cls = MagicMock()
    return mock_database

class TestRunScriptWorker:
    """Test RunScriptWorker class."""

    @pytest.fixture
    def worker(self):
        """Create a RunScriptWorker instance for testing."""
        with patch("mindtrace.cluster.core.cluster.UnifiedMindtraceODMBackend") as MockDatabase:
            MockDatabase.return_value = create_mock_database()
            worker = RunScriptWorker()
            
        worker.start()
        return worker

    @pytest.fixture
    def git_job_dict(self):
        """Create a job dictionary with git environment configuration."""
        return {
            "environment": {
                "git": {
                    "repo_url": "https://github.com/test-owner/test-repo.git",
                    "branch": "main",
                    "commit": "abc123",
                    "working_dir": "src"
                }
            },
            "command": "python script.py"
        }

    @pytest.fixture
    def docker_job_dict(self):
        """Create a job dictionary with docker environment configuration."""
        return {
            "environment": {
                "docker": {
                    "image": "python:3.9",
                    "working_dir": "/workspace",
                    "environment": {"PYTHONPATH": "/workspace"},
                    "volumes": {"/host/path": {"bind": "/container/path", "mode": "rw"}}
                }
            },
            "command": "python script.py"
        }

    def test_initialization(self, worker):
        """Test RunScriptWorker initialization."""
        assert worker.env_manager is None
        assert worker.working_dir is None
        assert worker.container_id is None

    @patch('mindtrace.cluster.workers.run_script_worker.GitEnvironment')
    def test_setup_environment_git(self, mock_git_env_class, worker, git_job_dict):
        """Test environment setup with git configuration."""
        # Mock GitEnvironment
        mock_git_env = Mock()
        mock_git_env.setup.return_value = "/tmp/test-repo-123/src"
        mock_git_env_class.return_value = mock_git_env

        worker.setup_environment(git_job_dict["environment"])

        # Verify GitEnvironment was created with correct parameters
        mock_git_env_class.assert_called_once_with(
            repo_url="https://github.com/test-owner/test-repo.git",
            branch="main",
            commit="abc123",
            working_dir="src"
        )
        
        # Verify setup was called
        mock_git_env.setup.assert_called_once()
        
        # Verify worker attributes were set
        assert worker.env_manager == mock_git_env
        assert worker.working_dir == "/tmp/test-repo-123/src"

    @patch('mindtrace.cluster.workers.run_script_worker.DockerEnvironment')
    @patch.dict(os.environ, {"GOOGLE_APPLICATION_CREDENTIALS": "/path/to/credentials.json"})
    def test_setup_environment_docker(self, mock_docker_env_class, worker, docker_job_dict):
        """Test environment setup with docker configuration."""
        # Mock DockerEnvironment
        mock_docker_env = Mock()
        mock_docker_env.setup.return_value = "test-container-id"
        mock_docker_env_class.return_value = mock_docker_env

        worker.setup_environment(docker_job_dict["environment"])

        # Verify DockerEnvironment was created with correct parameters
        mock_docker_env_class.assert_called_once_with(
            image="python:3.9",
            working_dir="/workspace",
            environment={"PYTHONPATH": "/workspace"},
            volumes={"/host/path": {"bind": "/container/path", "mode": "rw"}}
        )
        
        # Verify setup was called
        mock_docker_env.setup.assert_called_once()
        
        # Verify worker attributes were set
        assert worker.env_manager == mock_docker_env
        assert worker.container_id == "test-container-id"

    @patch('mindtrace.cluster.workers.run_script_worker.DockerEnvironment')
    @patch.dict(os.environ, {"GOOGLE_APPLICATION_CREDENTIALS": "/path/to/credentials.json"})
    def test_setup_environment_docker_with_gcp_credentials(self, mock_docker_env_class, worker):
        """Test environment setup with docker configuration including GCP credentials."""
        job_dict = {
            "environment": {
                "docker": {
                    "image": "python:3.9",
                    "volumes": {
                        "GCP_CREDENTIALS": "/container/credentials.json",
                        "/other/path": {"bind": "/other/container/path", "mode": "rw"}
                    }
                }
            }
        }

        # Mock DockerEnvironment
        mock_docker_env = Mock()
        mock_docker_env.setup.return_value = "test-container-id"
        mock_docker_env_class.return_value = mock_docker_env

        worker.setup_environment(job_dict["environment"])

        # Verify GCP_CREDENTIALS was replaced with actual credentials path
        expected_volumes = {
            "/path/to/credentials.json": "/container/credentials.json",
            "/other/path": {"bind": "/other/container/path", "mode": "rw"}
        }
        
        mock_docker_env_class.assert_called_once_with(
            image="python:3.9",
            working_dir=None,
            environment={},
            volumes=expected_volumes
        )

    def test_setup_environment_invalid_config(self, worker):
        """Test environment setup with invalid configuration."""
        job_dict = {
            "environment": {
                "invalid_env": {
                    "some": "config"
                }
            }
        }

        with pytest.raises(ValueError, match="No valid environment configuration in job data"):
            worker.setup_environment(job_dict["environment"])

    def test_setup_environment_empty_config(self, worker):
        """Test environment setup with empty configuration."""
        job_dict = {
            "environment": {}
        }

        with pytest.raises(ValueError, match="No valid environment configuration in job data"):
            worker.setup_environment(job_dict["environment"])

    @patch('mindtrace.cluster.workers.run_script_worker.GitEnvironment')
    def test_run_success(self, mock_git_env_class, worker, git_job_dict):
        """Test successful job execution."""
        # Mock GitEnvironment
        mock_git_env = Mock()
        mock_git_env.setup.return_value = "/tmp/test-repo-123/src"
        mock_git_env.execute.return_value = (0, "Command output", "")
        mock_git_env_class.return_value = mock_git_env

        result = worker._run(git_job_dict)

        assert result["status"] == "completed"
        assert result["output"]["stdout"] == "Command output"
        assert result["output"]["stderr"] == ""
        
        # Verify environment was set up and cleaned up
        mock_git_env.setup.assert_called_once()
        mock_git_env.execute.assert_called_once_with("python script.py")
        mock_git_env.cleanup.assert_called_once()

    @patch('mindtrace.cluster.workers.run_script_worker.GitEnvironment')
    def test_run_failure(self, mock_git_env_class, worker, git_job_dict):
        """Test job execution with command failure."""
        # Mock GitEnvironment
        mock_git_env = Mock()
        mock_git_env.setup.return_value = "/tmp/test-repo-123/src"
        mock_git_env.execute.return_value = (1, "Command output", "Error message")
        mock_git_env_class.return_value = mock_git_env

        result = worker._run(git_job_dict)

        assert result["status"] == "failed"
        assert result["output"]["stdout"] == "Command output"
        assert result["output"]["stderr"] == "Error message"
        
        # Verify environment was cleaned up even on failure
        mock_git_env.cleanup.assert_called_once()

    @patch('mindtrace.cluster.workers.run_script_worker.GitEnvironment')
    def test_run_exception(self, mock_git_env_class, worker, git_job_dict):
        """Test job execution with exception."""
        # Mock GitEnvironment
        mock_git_env = Mock()
        mock_git_env.setup.return_value = "/tmp/test-repo-123/src"
        mock_git_env.execute.side_effect = RuntimeError("Execution failed")
        mock_git_env_class.return_value = mock_git_env

        with pytest.raises(RuntimeError, match="Execution failed"):
            worker._run(git_job_dict)
        
        # Verify environment was cleaned up even on exception
        mock_git_env.cleanup.assert_called_once()

    @patch('mindtrace.cluster.workers.run_script_worker.GitEnvironment')
    def test_run_setup_exception(self, mock_git_env_class, worker, git_job_dict):
        """Test job execution with setup exception."""
        # Mock GitEnvironment setup to fail
        mock_git_env = Mock()
        mock_git_env.setup.side_effect = RuntimeError("Setup failed")
        mock_git_env_class.return_value = mock_git_env

        with pytest.raises(RuntimeError, match="Setup failed"):
            worker._run(git_job_dict)
        
        # Verify cleanup was called even though setup failed
        mock_git_env.cleanup.assert_called_once()

    def test_cleanup_environment_with_git(self, worker):
        """Test environment cleanup with git environment."""
        # Setup mock environment
        mock_env_manager = Mock()
        worker.env_manager = mock_env_manager
        worker.working_dir = "/tmp/test-repo-123/src"

        worker.cleanup_environment()

        mock_env_manager.cleanup.assert_called_once()
        assert worker.env_manager is None
        assert worker.working_dir is None

    def test_cleanup_environment_with_docker(self, worker):
        """Test environment cleanup with docker environment."""
        # Setup mock environment
        mock_env_manager = Mock()
        worker.env_manager = mock_env_manager
        worker.container_id = "test-container-id"

        worker.cleanup_environment()

        mock_env_manager.cleanup.assert_called_once()
        assert worker.env_manager is None
        assert worker.container_id is None

    def test_cleanup_environment_without_env_manager(self, worker):
        """Test environment cleanup without environment manager."""
        # Ensure no environment manager is set
        worker.env_manager = None
        worker.working_dir = "/tmp/test-repo-123/src"
        worker.container_id = "test-container-id"

        worker.cleanup_environment()

        assert worker.env_manager is None
        assert worker.working_dir is None
        assert worker.container_id is None

    def test_prepare_devices_cpu(self, worker):
        """Test device preparation for CPU-only execution."""
        worker.devices = None
        
        visible_devices, local_devices = worker.prepare_devices()
        
        assert visible_devices is None
        assert local_devices == "cpu"

    def test_prepare_devices_cpu_string(self, worker):
        """Test device preparation for CPU-only execution with string."""
        worker.devices = "cpu"
        
        visible_devices, local_devices = worker.prepare_devices()
        
        assert visible_devices is None
        assert local_devices == "cpu"

    def test_prepare_devices_auto(self, worker):
        """Test device preparation for auto device selection."""
        worker.devices = "auto"
        
        visible_devices, local_devices = worker.prepare_devices()
        
        assert visible_devices == ""
        assert local_devices == "auto"

    def test_prepare_devices_specific(self, worker):
        """Test device preparation for specific devices."""
        worker.devices = [0, 1, 2]
        
        visible_devices, local_devices = worker.prepare_devices()
        
        assert visible_devices == "0,1,2"
        assert local_devices == "0,1,2"

    def test_prepare_devices_single_device(self, worker):
        """Test device preparation for single device."""
        worker.devices = [0]
        
        visible_devices, local_devices = worker.prepare_devices()
        
        assert visible_devices == "0"
        assert local_devices == "0"


class TestRunScriptWorkerInput:
    """Test RunScriptWorkerInput model."""

    def test_initialization(self):
        """Test RunScriptWorkerInput initialization."""
        input_data = RunScriptWorkerInput(
            environment={"git": {"repo_url": "https://github.com/test/repo.git"}},
            command="python script.py"
        )

        assert input_data.environment == {"git": {"repo_url": "https://github.com/test/repo.git"}}
        assert input_data.command == "python script.py"

    def test_model_dump(self):
        """Test RunScriptWorkerInput model_dump method."""
        input_data = RunScriptWorkerInput(
            environment={"docker": {"image": "python:3.9"}},
            command="echo hello"
        )

        result = input_data.model_dump()

        expected = {
            "environment": {"docker": {"image": "python:3.9"}},
            "command": "echo hello"
        }
        assert result == expected


class TestRunScriptWorkerOutput:
    """Test RunScriptWorkerOutput model."""

    def test_initialization(self):
        """Test RunScriptWorkerOutput initialization."""
        output_data = RunScriptWorkerOutput(
            output="Command output",
            error="Error message"
        )

        assert output_data.output == "Command output"
        assert output_data.error == "Error message"

    def test_model_dump(self):
        """Test RunScriptWorkerOutput model_dump method."""
        output_data = RunScriptWorkerOutput(
            output="Success output",
            error=""
        )

        result = output_data.model_dump()

        expected = {
            "output": "Success output",
            "error": ""
        }
        assert result == expected 
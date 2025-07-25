from unittest.mock import Mock, patch

import pytest
from docker.errors import DockerException

from mindtrace.cluster.workers.environments.docker_env import DockerEnvironment


class TestDockerEnvironment:
    """Test DockerEnvironment class."""

    @pytest.fixture
    def docker_env(self):
        """Create a DockerEnvironment instance for testing."""
        return DockerEnvironment(
            image="test-image:latest",
            environment={"TEST_VAR": "test_value"},
            volumes={"/host/path": {"bind": "/container/path", "mode": "rw"}},
            devices=["0", "1"],
            working_dir="/workspace"
        )

    @pytest.fixture
    def mock_docker_client(self):
        """Mock Docker client."""
        with patch('mindtrace.cluster.workers.environments.docker_env.docker.from_env') as mock_client:
            # Mock the client and its components
            mock_client.return_value.images.pull = Mock()
            mock_client.return_value.containers.run = Mock()
            yield mock_client

    @pytest.fixture
    def docker_env_with_mock(self, mock_docker_client):
        """Create a DockerEnvironment instance with mocked Docker client."""
        return DockerEnvironment(
            image="test-image:latest",
            environment={"TEST_VAR": "test_value"},
            volumes={"/host/path": {"bind": "/container/path", "mode": "rw"}},
            devices=["0", "1"],
            working_dir="/workspace"
        )

    def test_initialization(self):
        """Test DockerEnvironment initialization with all parameters."""
        env = DockerEnvironment(
            image="test-image:latest",
            environment={"TEST_VAR": "test_value"},
            volumes={"/host/path": {"bind": "/container/path", "mode": "rw"}},
            devices=["0", "1"],
            working_dir="/workspace"
        )

        assert env.image == "test-image:latest"
        assert env.environment == {"TEST_VAR": "test_value"}
        assert env.volumes == {"/host/path": {"bind": "/container/path", "mode": "rw"}}
        assert env.devices == ["0", "1"]
        assert env.working_dir == "/workspace"
        assert env.container is None

    def test_initialization_with_defaults(self):
        """Test DockerEnvironment initialization with default values."""
        env = DockerEnvironment(image="test-image:latest")

        assert env.image == "test-image:latest"
        assert env.environment == {}
        assert env.volumes == {}
        assert env.devices == []
        assert env.working_dir is None
        assert env.container is None

    def test_setup_success(self, docker_env_with_mock, mock_docker_client):
        """Test successful container setup."""
        # Mock the Docker client and container
        mock_container = Mock()
        mock_container.id = "test-container-id"
        mock_docker_client.return_value.containers.run.return_value = mock_container

        container_id = docker_env_with_mock.setup()

        assert container_id == "test-container-id"
        assert docker_env_with_mock.container == mock_container
        mock_docker_client.return_value.images.pull.assert_called_once_with("test-image:latest")
        mock_docker_client.return_value.containers.run.assert_called_once()

    def test_setup_with_device_requests(self, mock_docker_client):
        """Test container setup with GPU device requests."""
        env = DockerEnvironment(
            image="test-image:latest",
            devices=["0", "1"]
        )

        mock_container = Mock()
        mock_container.id = "test-container-id"
        mock_docker_client.return_value.containers.run.return_value = mock_container

        container_id = env.setup()

        assert container_id == "test-container-id"
        # Verify device_requests was called with proper parameters
        call_args = mock_docker_client.return_value.containers.run.call_args
        device_requests = call_args[1]['device_requests']
        assert len(device_requests) == 1
        assert device_requests[0].device_ids == ["0", "1"]
        assert device_requests[0].capabilities == [["gpu"]]

    def test_setup_without_devices(self, mock_docker_client):
        """Test container setup without GPU devices."""
        env = DockerEnvironment(
            image="test-image:latest",
            devices=[]
        )

        mock_container = Mock()
        mock_container.id = "test-container-id"
        mock_docker_client.return_value.containers.run.return_value = mock_container

        container_id = env.setup()

        assert container_id == "test-container-id"
        # Verify device_requests was called with empty device list
        call_args = mock_docker_client.return_value.containers.run.call_args
        device_requests = call_args[1]['device_requests']
        assert len(device_requests) == 1
        assert device_requests[0].device_ids == []

    def test_setup_image_pull_failure(self, docker_env_with_mock, mock_docker_client):
        """Test setup failure when image pull fails."""
        mock_docker_client.return_value.images.pull.side_effect = DockerException("Image not found")

        with pytest.raises(RuntimeError, match="Failed to setup docker environment: Image not found"):
            docker_env_with_mock.setup()

        assert docker_env_with_mock.container is None

    def test_setup_container_run_failure(self, docker_env_with_mock, mock_docker_client):
        """Test setup failure when container run fails."""
        mock_docker_client.return_value.containers.run.side_effect = DockerException("Container run failed")

        with pytest.raises(RuntimeError, match="Failed to setup docker environment: Container run failed"):
            docker_env_with_mock.setup()

        assert docker_env_with_mock.container is None

    def test_execute_success(self, docker_env_with_mock, mock_docker_client):
        """Test successful command execution."""
        # Setup container
        mock_container = Mock()
        mock_container.id = "test-container-id"
        mock_docker_client.return_value.containers.run.return_value = mock_container
        docker_env_with_mock.setup()

        # Mock exec_run
        mock_container.exec_run.return_value = (0, (b"stdout output", b"stderr output"))

        exit_code, stdout, stderr = docker_env_with_mock.execute("test command")

        assert exit_code == 0
        assert stdout == "stdout output"
        assert stderr == "stderr output"
        mock_container.exec_run.assert_called_once_with("test command", workdir="/workspace", demux=True)

    def test_execute_list_command(self, docker_env_with_mock, mock_docker_client):
        """Test command execution with list command."""
        # Setup container
        mock_container = Mock()
        mock_container.id = "test-container-id"
        mock_docker_client.return_value.containers.run.return_value = mock_container
        docker_env_with_mock.setup()

        # Mock exec_run
        mock_container.exec_run.return_value = (0, (b"stdout output", b""))

        exit_code, stdout, stderr = docker_env_with_mock.execute(["echo", "hello", "world"])

        assert exit_code == 0
        assert stdout == "stdout output"
        assert stderr == ""
        mock_container.exec_run.assert_called_once_with("echo hello world", workdir="/workspace", demux=True)

    def test_execute_without_container(self, docker_env):
        """Test execute without initialized container."""
        with pytest.raises(RuntimeError, match="Container not initialized"):
            docker_env.execute("test command")

    def test_execute_with_empty_output(self, docker_env_with_mock, mock_docker_client):
        """Test command execution with empty output."""
        # Setup container
        mock_container = Mock()
        mock_container.id = "test-container-id"
        mock_docker_client.return_value.containers.run.return_value = mock_container
        docker_env_with_mock.setup()

        # Mock exec_run with None outputs
        mock_container.exec_run.return_value = (1, (None, None))

        exit_code, stdout, stderr = docker_env_with_mock.execute("test command")

        assert exit_code == 1
        assert stdout == ""
        assert stderr == ""

    def test_cleanup_success(self, docker_env_with_mock, mock_docker_client):
        """Test successful container cleanup."""
        # Setup container
        mock_container = Mock()
        mock_container.id = "test-container-id"
        mock_docker_client.return_value.containers.run.return_value = mock_container
        docker_env_with_mock.setup()

        docker_env_with_mock.cleanup()

        mock_container.stop.assert_called_once()
        mock_container.remove.assert_called_once()
        assert docker_env_with_mock.container is None

    def test_cleanup_with_docker_exception(self, docker_env_with_mock, mock_docker_client):
        """Test cleanup with Docker exception (should not raise)."""
        # Setup container
        mock_container = Mock()
        mock_container.id = "test-container-id"
        mock_docker_client.return_value.containers.run.return_value = mock_container
        docker_env_with_mock.setup()

        # Mock DockerException during cleanup
        mock_container.stop.side_effect = DockerException("Container already stopped")

        # Should not raise exception
        docker_env_with_mock.cleanup()

        assert docker_env_with_mock.container is None

    def test_cleanup_without_container(self, docker_env):
        """Test cleanup without container (should not raise)."""
        docker_env.cleanup()
        assert docker_env.container is None

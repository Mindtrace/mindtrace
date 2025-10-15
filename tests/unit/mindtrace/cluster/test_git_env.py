import os
import subprocess
import tempfile
from unittest.mock import Mock, patch

import git
import pytest

from mindtrace.cluster.workers.environments.git_env import GitEnvironment


class TestGitEnvironment:
    """Test GitEnvironment class."""

    @pytest.fixture
    def git_env(self):
        """Create a GitEnvironment instance for testing."""
        return GitEnvironment(
            repo_url="https://github.com/test-owner/test-repo.git", branch="main", commit="abc123", working_dir="src"
        )

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    @pytest.fixture(autouse=True)
    def _env_config(self, monkeypatch):
        """Provide TEMP_DIR via env so GitEnvironment picks it up through CoreConfig."""
        monkeypatch.setenv("MINDTRACE_DIR_PATHS__TEMP_DIR", "/tmp/mindtrace")

    def test_initialization(self):
        """Test GitEnvironment initialization with all parameters."""
        env = GitEnvironment(
            repo_url="https://github.com/test-owner/test-repo.git", branch="main", commit="abc123", working_dir="src"
        )

        assert env.repo_url == "https://github.com/test-owner/test-repo.git"
        assert env.branch == "main"
        assert env.commit == "abc123"
        assert env.working_dir == "src"
        assert env.temp_dir is None
        assert env.repo is None
        assert env.allowed_owners == ["Mindtrace"]

    def test_initialization_with_defaults(self):
        """Test GitEnvironment initialization with default values."""
        env = GitEnvironment(repo_url="https://github.com/test-owner/test-repo.git")

        assert env.repo_url == "https://github.com/test-owner/test-repo.git"
        assert env.branch is None
        assert env.commit is None
        assert env.working_dir is None
        assert env.temp_dir is None
        assert env.repo is None

    def test_extract_repo_owner_success(self, git_env):
        """Test successful repository owner extraction."""
        owner = git_env._extract_repo_owner("https://github.com/test-owner/test-repo.git")
        assert owner == "test-owner"

    def test_extract_repo_owner_without_git_suffix(self, git_env):
        """Test repository owner extraction without .git suffix."""
        owner = git_env._extract_repo_owner("https://github.com/test-owner/test-repo")
        assert owner == "test-owner"

    def test_extract_repo_owner_unsupported_url(self, git_env):
        """Test repository owner extraction with unsupported URL."""
        with pytest.raises(ValueError, match="Unsupported repository URL: https://gitlab.com/test/repo.git"):
            git_env._extract_repo_owner("https://gitlab.com/test/repo.git")

    def test_extract_repo_owner_malformed_url(self, git_env):
        """Test repository owner extraction with malformed URL."""
        with pytest.raises(ValueError, match="Unsupported repository URL: https://github.com"):
            git_env._extract_repo_owner("https://github.com")

    @patch("tempfile.mkdtemp")
    @patch("pathlib.Path.mkdir")
    def test_setup_success(self, mock_mkdir, mock_mkdtemp, git_env):
        """Test successful environment setup."""
        # Mock temp directory creation
        mock_mkdtemp.return_value = "/tmp/test-repo-123"

        # Mock repository cloning
        mock_repo = Mock()
        mock_repo.git.checkout = Mock()
        git_env._clone_repository = Mock()
        git_env._clone_repository.return_value = None
        git_env.repo = mock_repo

        # Mock working directory
        git_env._get_working_dir = Mock()
        git_env._get_working_dir.return_value = "/tmp/test-repo-123/src"

        # Mock dependency syncing
        git_env._sync_dependencies = Mock()

        working_dir = git_env.setup()

        assert working_dir == "/tmp/test-repo-123/src"
        assert git_env.temp_dir == "/tmp/test-repo-123"
        mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)
        git_env._clone_repository.assert_called_once()
        git_env._get_working_dir.assert_called_once()
        git_env._sync_dependencies.assert_called_once_with("/tmp/test-repo-123/src")

    @patch("tempfile.mkdtemp")
    def test_setup_failure_cleanup(self, mock_mkdtemp, git_env):
        """Test setup failure triggers cleanup."""
        # Mock temp directory creation
        mock_mkdtemp.return_value = "/tmp/test-repo-123"

        # Mock cleanup method
        git_env.cleanup = Mock()

        # Mock _clone_repository to raise exception
        git_env._clone_repository = Mock()
        git_env._clone_repository.side_effect = RuntimeError("Clone failed")

        with pytest.raises(RuntimeError, match="Failed to setup git environment: Clone failed"):
            git_env.setup()

        git_env.cleanup.assert_called_once()

    def test_remove_git_auth_methods(self, git_env):
        """Test git authentication methods removal."""
        # Set some environment variables
        os.environ["GIT_USERNAME"] = "test_user"
        os.environ["GIT_PASSWORD"] = "test_pass"

        git_env._remove_git_auth_methods()

        assert os.environ["GIT_ASKPASS"] == "echo"
        assert os.environ["GIT_TERMINAL_PROMPT"] == "0"
        assert os.environ["GIT_CREDENTIAL_HELPER"] == "none"
        assert os.environ["GIT_SSH_COMMAND"] == "ssh -o IdentitiesOnly=yes -i /dev/null"
        assert os.environ["GIT_CONFIG_GLOBAL"] == "0"
        assert os.environ["GIT_CONFIG_SYSTEM"] == "0"
        assert "GIT_USERNAME" not in os.environ
        assert "GIT_PASSWORD" not in os.environ

    @patch.dict(os.environ, {"GIT_FINE_GRAINED_TOKEN": "test_token"})
    def test_get_token_allowed_owner(self, git_env):
        """Test token retrieval for allowed owner."""
        git_env.allowed_owners = ["test-owner"]

        token = git_env._get_token()

        assert token == "test_token"

    def test_get_token_not_allowed_owner(self, git_env):
        """Test token retrieval for non-allowed owner."""
        git_env.allowed_owners = ["other-owner"]

        token = git_env._get_token()

        assert token is None

    def test_get_token_no_env_var(self, git_env):
        """Test token retrieval when no environment variable is set."""
        # Ensure no token in environment
        if "GIT_FINE_GRAINED_TOKEN" in os.environ:
            del os.environ["GIT_FINE_GRAINED_TOKEN"]

        token = git_env._get_token()

        assert token is None

    @patch("git.Repo.clone_from")
    def test_clone_repository_with_token(self, mock_clone, git_env):
        """Test repository cloning with authentication token."""
        # Mock token retrieval
        git_env._get_token = Mock()
        git_env._get_token.return_value = "test_token"
        git_env.temp_dir = "/tmp/test-repo-123"

        # Mock repository
        mock_repo = Mock()
        mock_repo.git.checkout = Mock()
        mock_clone.return_value = mock_repo

        git_env._clone_repository()

        # Verify clone was called with token
        expected_url = "https://test_token@github.com/test-owner/test-repo.git"
        mock_clone.assert_called_once_with(expected_url, "/tmp/test-repo-123")
        assert git_env.repo == mock_repo

    @patch("git.Repo.clone_from")
    def test_clone_repository_without_token(self, mock_clone, git_env):
        """Test repository cloning without authentication token."""
        # Mock token retrieval
        git_env._get_token = Mock()
        git_env._get_token.return_value = None
        git_env.temp_dir = "/tmp/test-repo-123"

        # Mock repository
        mock_repo = Mock()
        mock_repo.git.checkout = Mock()
        mock_clone.return_value = mock_repo

        git_env._clone_repository()

        # Verify clone was called without token
        mock_clone.assert_called_once_with("https://github.com/test-owner/test-repo.git", "/tmp/test-repo-123")
        assert git_env.repo == mock_repo

    @patch("git.Repo.clone_from")
    def test_clone_repository_authentication_failure(self, mock_clone, git_env):
        """Test repository cloning with authentication failure."""
        git_env._get_token = Mock()
        git_env._get_token.return_value = None
        git_env.temp_dir = "/tmp/test-repo-123"

        mock_clone.side_effect = git.GitCommandError("git", 128, "Authentication failed")

        with pytest.raises(RuntimeError, match="Authentication failed for https://github.com/test-owner/test-repo.git"):
            git_env._clone_repository()

    @patch("git.Repo.clone_from")
    def test_clone_repository_general_failure(self, mock_clone, git_env):
        """Test repository cloning with general failure."""
        git_env._get_token = Mock()
        git_env._get_token.return_value = None

        mock_clone.side_effect = Exception("Network error")

        with pytest.raises(RuntimeError, match="Failed to clone repository: Network error"):
            git_env._clone_repository()

    @patch("git.Repo.clone_from")
    def test_clone_repository_with_commit_checkout(self, mock_clone, git_env):
        """Test repository cloning with specific commit checkout."""
        git_env._get_token = Mock()
        git_env._get_token.return_value = None
        git_env.branch = None

        mock_repo = Mock()
        mock_repo.git.checkout = Mock()
        mock_clone.return_value = mock_repo

        git_env._clone_repository()

        # Verify commit checkout
        mock_repo.git.checkout.assert_called_with("abc123")

    @patch("git.Repo.clone_from")
    def test_clone_repository_with_branch_checkout(self, mock_clone, git_env):
        """Test repository cloning with specific branch checkout."""
        git_env._get_token = Mock()
        git_env._get_token.return_value = None

        mock_repo = Mock()
        mock_repo.git.checkout = Mock()
        mock_clone.return_value = mock_repo

        git_env._clone_repository()

        # Verify branch checkout
        mock_repo.git.checkout.assert_called_with("main")

    @patch("git.Repo.clone_from")
    def test_clone_repository_checkout_failure(self, mock_clone, git_env):
        """Test repository cloning with checkout failure."""
        git_env._get_token = Mock()
        git_env._get_token.return_value = None
        git_env.branch = None

        mock_repo = Mock()
        mock_repo.git.checkout = Mock()
        mock_repo.git.checkout.side_effect = git.GitCommandError("git", 128, "Commit not found")
        mock_clone.return_value = mock_repo

        with pytest.raises(
            RuntimeError, match="Failed to checkout commit abc123: Cmd\\('git'\\) failed due to: exit code\\(128\\)"
        ):
            git_env._clone_repository()

    def test_get_working_dir_with_subdirectory(self, git_env):
        """Test working directory retrieval with subdirectory."""
        git_env.temp_dir = "/tmp/test-repo-123"
        git_env.working_dir = "src"

        with patch("os.path.exists", return_value=True):
            working_dir = git_env._get_working_dir()

        assert working_dir == "/tmp/test-repo-123/src"

    def test_get_working_dir_without_subdirectory(self, git_env):
        """Test working directory retrieval without subdirectory."""
        git_env.temp_dir = "/tmp/test-repo-123"
        git_env.working_dir = None

        working_dir = git_env._get_working_dir()

        assert working_dir == "/tmp/test-repo-123"

    def test_get_working_dir_nonexistent(self, git_env):
        """Test working directory retrieval with nonexistent directory."""
        git_env.temp_dir = "/tmp/test-repo-123"
        git_env.working_dir = "nonexistent"

        with patch("os.path.exists", return_value=False):
            with pytest.raises(RuntimeError, match="Working directory /tmp/test-repo-123/nonexistent does not exist"):
                git_env._get_working_dir()

    @patch("subprocess.run")
    def test_sync_dependencies_success(self, mock_run, git_env):
        """Test successful dependency synchronization."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        git_env._sync_dependencies("/tmp/test-repo-123")

        mock_run.assert_called_once_with(
            ["uv", "sync"], cwd="/tmp/test-repo-123", capture_output=True, text=True, check=True
        )

    @patch("subprocess.run")
    def test_sync_dependencies_failure(self, mock_run, git_env):
        """Test dependency synchronization failure."""
        mock_run.side_effect = subprocess.CalledProcessError(1, "uv sync", stderr="Dependency error")

        with pytest.raises(subprocess.CalledProcessError, match="Command 'uv sync' returned non-zero exit status 1"):
            git_env._sync_dependencies("/tmp/test-repo-123")

    @patch("shutil.rmtree")
    def test_cleanup_success(self, mock_rmtree, git_env):
        """Test successful cleanup."""
        git_env.temp_dir = "/tmp/test-repo-123"
        git_env.repo = Mock()

        with patch("os.path.exists", return_value=True):
            git_env.cleanup()

        mock_rmtree.assert_called_once_with("/tmp/test-repo-123")
        assert git_env.temp_dir is None
        assert git_env.repo is None

    @patch("shutil.rmtree")
    def test_cleanup_nonexistent_directory(self, mock_rmtree, git_env):
        """Test cleanup with nonexistent directory."""
        git_env.temp_dir = "/tmp/test-repo-123"

        with patch("os.path.exists", return_value=False):
            git_env.cleanup()

        mock_rmtree.assert_not_called()
        assert git_env.temp_dir is None
        assert git_env.repo is None

    @patch("shutil.rmtree")
    def test_cleanup_without_temp_dir(self, mock_rmtree, git_env):
        """Test cleanup without temp directory."""
        git_env.temp_dir = None

        git_env.cleanup()

        mock_rmtree.assert_not_called()
        assert git_env.temp_dir is None
        assert git_env.repo is None

    @patch("subprocess.run")
    @patch("os.path.exists")
    def test_execute_success(self, mock_exists, mock_run, git_env):
        """Test successful command execution."""
        git_env.temp_dir = "/tmp/test-repo-123"
        mock_exists.return_value = True

        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "Command output"
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        exit_code, stdout, stderr = git_env.execute("python script.py")

        assert exit_code == 0
        assert stdout == "Command output"
        assert stderr == ""
        mock_run.assert_called_once()

    @patch("subprocess.run")
    @patch("os.path.exists")
    def test_execute_list_command(self, mock_exists, mock_run, git_env):
        """Test command execution with list command."""
        git_env.temp_dir = "/tmp/test-repo-123"
        mock_exists.return_value = True

        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "List command output"
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        exit_code, stdout, stderr = git_env.execute(["python", "script.py", "--arg", "value"])

        assert exit_code == 0
        assert stdout == "List command output"
        assert stderr == ""
        # Verify command was joined
        call_args = mock_run.call_args
        assert "python script.py --arg value" in call_args[0][0]

    @patch("subprocess.run")
    @patch("os.path.exists")
    def test_execute_without_uv_prefix(self, mock_exists, mock_run, git_env):
        """Test command execution without uv prefix."""
        git_env.temp_dir = "/tmp/test-repo-123"
        mock_exists.return_value = True

        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "Output"
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        git_env.execute("python script.py")

        # Verify uv run was prepended
        call_args = mock_run.call_args
        assert call_args[0][0] == "uv run python script.py"

    @patch("subprocess.run")
    @patch("os.path.exists")
    def test_execute_with_uv_prefix(self, mock_exists, mock_run, git_env):
        """Test command execution with uv prefix."""
        git_env.temp_dir = "/tmp/test-repo-123"
        mock_exists.return_value = True

        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "Output"
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        git_env.execute("uv run python script.py")

        # Verify uv run was not duplicated
        call_args = mock_run.call_args
        assert call_args[0][0] == "uv run python script.py"

    @patch("subprocess.run")
    @patch("os.path.exists")
    def test_execute_with_custom_environment(self, mock_exists, mock_run, git_env):
        """Test command execution with custom environment variables."""
        git_env.temp_dir = "/tmp/test-repo-123"
        mock_exists.return_value = True

        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "Output"
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        custom_env = {"CUSTOM_VAR": "custom_value"}
        git_env.execute("python script.py", env=custom_env)

        # Verify environment was passed
        call_args = mock_run.call_args
        assert call_args[1]["env"]["CUSTOM_VAR"] == "custom_value"

    @patch("subprocess.run")
    def test_execute_with_custom_working_directory(self, mock_run, git_env):
        """Test command execution with custom working directory."""
        git_env.temp_dir = "/tmp/test-repo-123"

        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "Output"
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        git_env.execute("python script.py", cwd="/custom/path")

        # Verify custom working directory was used
        call_args = mock_run.call_args
        assert call_args[1]["cwd"] == "/custom/path"

    @patch("os.path.exists")
    @patch("subprocess.run")
    def test_execute_subprocess_exception(self, mock_run, mock_exists, git_env):
        """Test command execution with subprocess exception."""
        git_env.temp_dir = "/tmp/test-repo-123"

        mock_exists.return_value = True
        mock_run.side_effect = Exception("Subprocess error")

        exit_code, stdout, stderr = git_env.execute("python script.py")

        assert exit_code == 1
        assert stdout == ""
        assert stderr == "Subprocess error"

    def test_execute_without_initialization(self, git_env):
        """Test command execution without initialization."""
        git_env.temp_dir = None

        with pytest.raises(RuntimeError, match="Git environment not initialized"):
            git_env.execute("python script.py")

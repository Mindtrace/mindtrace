import os
import pathlib
import shutil
import subprocess
import tempfile
from typing import Dict, List, Optional, Tuple, Union

import git

from mindtrace.core import Mindtrace


class GitEnvironment(Mindtrace):
    """Handles git repository setup and dependency management."""

    def __init__(
        self,
        repo_url: str,
        branch: Optional[str] = None,
        commit: Optional[str] = None,
        working_dir: Optional[str] = None,
    ):
        super().__init__()
        self.repo_url = repo_url
        self.branch = branch  # Use provided branch or get default from config
        self.commit = commit
        self.working_dir = working_dir
        self.temp_dir: str = None  # type: ignore
        self.repo = None
        self.allowed_owners = ["Mindtrace"]  # private allowed repos  TODO: get from env or config

    def _extract_repo_owner(self, url: str) -> str:
        """Extracts the repository identifier (owner/repo) from a GitHub URL.

        Example:
            "https://github.com/owner/repo.git" --> "owner/repo"
        """
        if "github.com" not in url:
            raise ValueError(f"Unsupported repository URL: {url}")
        try:
            parts = url.split("github.com/")[1]
            # Remove ".git" suffix if present.
            if parts.endswith(".git"):
                parts = parts[:-4]
            owner = parts.split("/")[0]
            return owner
        except IndexError:
            raise ValueError(f"Unsupported repository URL: {url}")

    def setup(self) -> str:
        """Setup git environment and return working directory."""
        try:
            # Create temp directory
            base_dir = pathlib.Path(self.config["MINDTRACE_DIR_PATHS"]["TEMP_DIR"])
            base_dir.mkdir(parents=True, exist_ok=True)
            self.temp_dir = tempfile.mkdtemp(dir=base_dir)

            # Clone repository
            self._clone_repository()

            # Setup working directory
            working_dir = self._get_working_dir()
            # Sync dependencies
            self._sync_dependencies(working_dir)
            return working_dir

        except Exception as e:
            self.cleanup()
            raise RuntimeError(f"Failed to setup git environment: {str(e)}") from e

    def _remove_git_auth_methods(self):
        """
        Remove git auth methods.
        """
        os.environ["GIT_ASKPASS"] = "echo"
        os.environ["GIT_TERMINAL_PROMPT"] = "0"
        os.environ["GIT_CREDENTIAL_HELPER"] = "none"
        os.environ["GIT_SSH_COMMAND"] = "ssh -o IdentitiesOnly=yes -i /dev/null"
        os.environ.pop("GIT_USERNAME", None)
        os.environ.pop("GIT_PASSWORD", None)
        os.environ["GIT_CONFIG_GLOBAL"] = "0"
        os.environ["GIT_CONFIG_SYSTEM"] = "0"

    def _get_token(self):
        """
        Priority:
        1. If a fine-grained token is provided via the environment variable "GIT_FINE_GRAINED_TOKEN"
            and the repository is on the allowed list, use it.
        2. Otherwise, attempt to clone the repository without a token.
        """
        repo_owner = self._extract_repo_owner(self.repo_url)

        if repo_owner in self.allowed_owners:
            token = os.environ.get("GIT_FINE_GRAINED_TOKEN")
            if token:
                self.logger.info(f"Using token: {token}")
                return token
        return None

    def _clone_repository(self):
        """Clone the repository.
        Raises:
            RuntimeError if no valid token is available and repository is not public.
        """
        self.logger.info(f"Cloning repo {self.repo_url}")
        token = self._get_token()
        try:
            self._remove_git_auth_methods()
            if token:
                if "github.com" in self.repo_url:
                    repo_name = self.repo_url.split("github.com/")[1]
                    repo_url_with_pat = f"https://{token}@github.com/{repo_name}"
                else:
                    raise RuntimeError(f"Unsupported repository URL: {self.repo_url}")
                self.repo = git.Repo.clone_from(repo_url_with_pat, self.temp_dir)
                self.logger.info("Successfully cloned repository with token")
            else:
                self.repo = git.Repo.clone_from(self.repo_url, self.temp_dir)
                self.logger.info("Successfully cloned repository without auth token")

        except git.GitCommandError as e:
            if "Authentication failed" in str(e):
                raise RuntimeError(f"Authentication failed for {self.repo_url}. Please provide a valid token.") from e
            raise RuntimeError(f"Failed to clone repository: {str(e)}") from e
        except Exception as e:
            raise RuntimeError(f"Failed to clone repository: {str(e)}") from e

        # Checkout specific commit/branch
        if self.commit:
            try:
                self.repo.git.checkout(self.commit)
                self.logger.info(f"Checked out commit {self.commit}")
            except git.GitCommandError as e:
                raise RuntimeError(f"Failed to checkout commit {self.commit}: {str(e)}")

        if self.branch:
            try:
                self.repo.git.checkout(self.branch)
                self.logger.info(f"Checked out branch {self.branch}")
            except git.GitCommandError as e:
                raise RuntimeError(f"Failed to checkout branch {self.branch}: {str(e)}")

    def _get_working_dir(self) -> str:
        """Get working directory path."""
        if self.working_dir:
            working_dir = os.path.join(self.temp_dir, self.working_dir)
            if not os.path.exists(working_dir):
                raise RuntimeError(f"Working directory {working_dir} does not exist")
            return working_dir
        return self.temp_dir

    def _sync_dependencies(self, working_dir: str):
        """Sync Python dependencies using uv."""
        self.logger.info(f"Running 'uv sync' in {working_dir}")
        result = subprocess.run(["uv", "sync"], cwd=working_dir, capture_output=True, text=True, check=True)
        if result.returncode != 0:
            raise RuntimeError(f"'uv sync' failed: {result.stderr}")
        self.logger.info("Dependencies synced successfully")

    def cleanup(self):
        """Cleanup temporary directory."""
        if self.temp_dir and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
        self.temp_dir = None  # type: ignore
        self.repo = None

    # TODO CHECK COMMAND USAGE FOR SHELL=TRYE CORRESPONDANCE(should be more usefully shell = False)
    def execute(
        self,
        command: Union[str, List[str]],
        env: Optional[Dict[str, str]] = None,
        cwd: Optional[str] = None,
        detach: bool = False,
    ) -> Tuple[int, str, str]:
        """Execute command in git synced environment.

        Args:
            command: Command to execute
            env: Environment variables
            cwd: Working directory

        Returns:
            tuple: (exit_code, stdout, stderr)
        """
        if not self.temp_dir:
            raise RuntimeError("Git environment not initialized")

        if detach:
            if isinstance(command, list):
                if not command[0].startswith("uv"):
                    command = ["uv", "run"] + command
            else:
                if not command.startswith("uv"):
                    command = ["uv run " + command]
        else:
            if isinstance(command, list):
                command = " ".join(command)

            if not command.startswith("uv"):
                command = "uv run " + command

        working_dir = cwd or self._get_working_dir()
        environment_vars = {**os.environ, **(env or {})}

        try:
            if not detach:
                result = subprocess.run(
                    command, shell=True, cwd=working_dir, env=environment_vars, capture_output=False, text=True
                )
                return result.returncode, result.stdout, result.stderr
            else:
                process = subprocess.Popen(command, cwd=working_dir, env=environment_vars)
                return process.pid, "", ""
        except Exception as e:
            return 1, "", str(e)

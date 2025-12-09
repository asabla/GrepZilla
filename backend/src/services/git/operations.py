"""Git operations service for cloning and updating repositories."""

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from backend.src.config.logging import get_logger
from backend.src.config.settings import get_settings
from backend.src.models.repository import AuthType

logger = get_logger(__name__)


@dataclass
class CloneResult:
    """Result of a clone or update operation."""

    success: bool
    repo_path: Path | None = None
    branch: str | None = None
    commit_sha: str | None = None
    error: str | None = None
    operation: Literal["clone", "fetch", "checkout"] | None = None


@dataclass
class GitCredentials:
    """Git credentials for repository access."""

    auth_type: AuthType
    token: str | None = None
    ssh_key_path: str | None = None
    username: str | None = None


class GitOperationsService:
    """Service for git clone and update operations."""

    def __init__(self) -> None:
        """Initialize the git operations service."""
        self._settings = get_settings()
        self._base_dir = Path(self._settings.git_clone_base_dir)
        self._timeout = self._settings.git_clone_timeout
        self._clone_depth = self._settings.git_clone_depth

    def _ensure_base_dir(self) -> None:
        """Ensure the base clone directory exists."""
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def _get_repo_path(self, repository_id: str) -> Path:
        """Get the local path for a repository.

        Args:
            repository_id: Repository UUID string.

        Returns:
            Path to the repository directory.
        """
        return self._base_dir / repository_id

    def _build_auth_url(
        self,
        git_url: str,
        credentials: GitCredentials | None,
    ) -> str:
        """Build git URL with embedded credentials if needed.

        Args:
            git_url: Original git URL.
            credentials: Optional credentials for authentication.

        Returns:
            Git URL with credentials embedded (for HTTPS) or original URL.
        """
        if credentials is None or credentials.auth_type == AuthType.NONE:
            return git_url

        if credentials.auth_type == AuthType.TOKEN and credentials.token:
            # For HTTPS URLs, embed token
            # https://github.com/user/repo.git -> https://token@github.com/user/repo.git
            if git_url.startswith("https://"):
                # Handle URLs that might already have credentials
                if "@" in git_url.split("//")[1].split("/")[0]:
                    # Already has credentials, replace them
                    protocol, rest = git_url.split("://", 1)
                    _, host_and_path = rest.split("@", 1)
                    return f"{protocol}://{credentials.token}@{host_and_path}"
                else:
                    return git_url.replace("https://", f"https://{credentials.token}@")

        # For SSH or other auth types, return original URL
        # SSH auth is handled via ssh-agent or deploy keys
        return git_url

    def _build_env(self, credentials: GitCredentials | None) -> dict[str, str]:
        """Build environment variables for git command.

        Args:
            credentials: Optional credentials for authentication.

        Returns:
            Environment dictionary for subprocess.
        """
        env = os.environ.copy()

        # Disable interactive prompts
        env["GIT_TERMINAL_PROMPT"] = "0"

        if credentials and credentials.auth_type == AuthType.SSH_KEY:
            if credentials.ssh_key_path:
                # Use specific SSH key
                env["GIT_SSH_COMMAND"] = (
                    f"ssh -i {credentials.ssh_key_path} "
                    "-o StrictHostKeyChecking=accept-new "
                    "-o BatchMode=yes"
                )

        return env

    def _run_git_command(
        self,
        args: list[str],
        cwd: Path | None = None,
        credentials: GitCredentials | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Run a git command.

        Args:
            args: Git command arguments (without 'git' prefix).
            cwd: Working directory for the command.
            credentials: Optional credentials for authentication.

        Returns:
            Completed process result.

        Raises:
            subprocess.TimeoutExpired: If command times out.
            subprocess.CalledProcessError: If command fails.
        """
        cmd = ["git"] + args
        env = self._build_env(credentials)

        logger.debug(
            "Running git command",
            command=cmd[0:2],  # Log only first two args for security
            cwd=str(cwd) if cwd else None,
        )

        return subprocess.run(
            cmd,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=self._timeout,
            check=True,
        )

    def _get_current_commit(self, repo_path: Path) -> str | None:
        """Get the current commit SHA.

        Args:
            repo_path: Path to the repository.

        Returns:
            Current commit SHA or None if failed.
        """
        try:
            result = self._run_git_command(
                ["rev-parse", "HEAD"],
                cwd=repo_path,
            )
            return result.stdout.strip()
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return None

    def _get_current_branch(self, repo_path: Path) -> str | None:
        """Get the current branch name.

        Args:
            repo_path: Path to the repository.

        Returns:
            Current branch name or None if in detached HEAD.
        """
        try:
            result = self._run_git_command(
                ["rev-parse", "--abbrev-ref", "HEAD"],
                cwd=repo_path,
            )
            branch = result.stdout.strip()
            return branch if branch != "HEAD" else None
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return None

    def clone_repository(
        self,
        git_url: str,
        repository_id: str,
        branch: str | None = None,
        credentials: GitCredentials | None = None,
    ) -> CloneResult:
        """Clone a repository.

        Args:
            git_url: Git repository URL.
            repository_id: Repository UUID string (used for local path).
            branch: Branch to clone (default: repository default).
            credentials: Optional credentials for authentication.

        Returns:
            CloneResult with success status and details.
        """
        self._ensure_base_dir()
        repo_path = self._get_repo_path(repository_id)

        logger.info(
            "Cloning repository",
            repository_id=repository_id,
            branch=branch,
            repo_path=str(repo_path),
        )

        # Remove existing directory if present
        if repo_path.exists():
            logger.warning(
                "Removing existing repository directory",
                repo_path=str(repo_path),
            )
            shutil.rmtree(repo_path)

        try:
            auth_url = self._build_auth_url(git_url, credentials)

            # Build clone command
            clone_args = ["clone"]

            if branch:
                clone_args.extend(["--branch", branch])

            if self._clone_depth:
                clone_args.extend(["--depth", str(self._clone_depth)])

            clone_args.extend([auth_url, str(repo_path)])

            self._run_git_command(clone_args, credentials=credentials)

            commit_sha = self._get_current_commit(repo_path)
            current_branch = self._get_current_branch(repo_path) or branch

            logger.info(
                "Repository cloned successfully",
                repository_id=repository_id,
                branch=current_branch,
                commit_sha=commit_sha,
            )

            return CloneResult(
                success=True,
                repo_path=repo_path,
                branch=current_branch,
                commit_sha=commit_sha,
                operation="clone",
            )

        except subprocess.TimeoutExpired:
            logger.error(
                "Clone timed out",
                repository_id=repository_id,
                timeout=self._timeout,
            )
            return CloneResult(
                success=False,
                error=f"Clone timed out after {self._timeout} seconds",
                operation="clone",
            )

        except subprocess.CalledProcessError as e:
            # Sanitize error message to remove potential credentials
            error_msg = self._sanitize_error(e.stderr or str(e))
            logger.error(
                "Clone failed",
                repository_id=repository_id,
                error=error_msg,
            )
            return CloneResult(
                success=False,
                error=error_msg,
                operation="clone",
            )

        except Exception as e:
            logger.error(
                "Unexpected error during clone",
                repository_id=repository_id,
                error=str(e),
            )
            return CloneResult(
                success=False,
                error=f"Unexpected error: {str(e)}",
                operation="clone",
            )

    def update_repository(
        self,
        repository_id: str,
        branch: str | None = None,
        credentials: GitCredentials | None = None,
    ) -> CloneResult:
        """Update an existing repository (fetch and checkout).

        Args:
            repository_id: Repository UUID string.
            branch: Branch to checkout (default: current branch).
            credentials: Optional credentials for authentication.

        Returns:
            CloneResult with success status and details.
        """
        repo_path = self._get_repo_path(repository_id)

        if not repo_path.exists():
            return CloneResult(
                success=False,
                error=f"Repository not found at {repo_path}",
                operation="fetch",
            )

        logger.info(
            "Updating repository",
            repository_id=repository_id,
            branch=branch,
            repo_path=str(repo_path),
        )

        try:
            # Fetch latest changes
            fetch_args = ["fetch", "--prune"]
            if self._clone_depth:
                fetch_args.extend(["--depth", str(self._clone_depth)])

            self._run_git_command(fetch_args, cwd=repo_path, credentials=credentials)

            # Checkout and pull the specified branch
            if branch:
                # Checkout the branch
                self._run_git_command(
                    ["checkout", branch],
                    cwd=repo_path,
                    credentials=credentials,
                )

            # Reset to remote tracking branch
            current_branch = self._get_current_branch(repo_path)
            if current_branch:
                self._run_git_command(
                    ["reset", "--hard", f"origin/{current_branch}"],
                    cwd=repo_path,
                    credentials=credentials,
                )

            commit_sha = self._get_current_commit(repo_path)

            logger.info(
                "Repository updated successfully",
                repository_id=repository_id,
                branch=current_branch,
                commit_sha=commit_sha,
            )

            return CloneResult(
                success=True,
                repo_path=repo_path,
                branch=current_branch,
                commit_sha=commit_sha,
                operation="fetch",
            )

        except subprocess.TimeoutExpired:
            logger.error(
                "Update timed out",
                repository_id=repository_id,
                timeout=self._timeout,
            )
            return CloneResult(
                success=False,
                error=f"Update timed out after {self._timeout} seconds",
                operation="fetch",
            )

        except subprocess.CalledProcessError as e:
            error_msg = self._sanitize_error(e.stderr or str(e))
            logger.error(
                "Update failed",
                repository_id=repository_id,
                error=error_msg,
            )
            return CloneResult(
                success=False,
                error=error_msg,
                operation="fetch",
            )

        except Exception as e:
            logger.error(
                "Unexpected error during update",
                repository_id=repository_id,
                error=str(e),
            )
            return CloneResult(
                success=False,
                error=f"Unexpected error: {str(e)}",
                operation="fetch",
            )

    def clone_or_update_repository(
        self,
        git_url: str,
        repository_id: str,
        branch: str | None = None,
        credentials: GitCredentials | None = None,
    ) -> CloneResult:
        """Clone a repository or update it if it already exists.

        Args:
            git_url: Git repository URL.
            repository_id: Repository UUID string.
            branch: Branch to clone/checkout.
            credentials: Optional credentials for authentication.

        Returns:
            CloneResult with success status and details.
        """
        repo_path = self._get_repo_path(repository_id)

        if repo_path.exists() and (repo_path / ".git").is_dir():
            logger.info(
                "Repository exists, updating",
                repository_id=repository_id,
            )
            return self.update_repository(
                repository_id=repository_id,
                branch=branch,
                credentials=credentials,
            )
        else:
            logger.info(
                "Repository does not exist, cloning",
                repository_id=repository_id,
            )
            return self.clone_repository(
                git_url=git_url,
                repository_id=repository_id,
                branch=branch,
                credentials=credentials,
            )

    def delete_repository(self, repository_id: str) -> bool:
        """Delete a cloned repository.

        Args:
            repository_id: Repository UUID string.

        Returns:
            True if deleted successfully, False otherwise.
        """
        repo_path = self._get_repo_path(repository_id)

        if not repo_path.exists():
            logger.debug(
                "Repository does not exist, nothing to delete",
                repository_id=repository_id,
            )
            return True

        try:
            shutil.rmtree(repo_path)
            logger.info(
                "Repository deleted",
                repository_id=repository_id,
                repo_path=str(repo_path),
            )
            return True
        except Exception as e:
            logger.error(
                "Failed to delete repository",
                repository_id=repository_id,
                error=str(e),
            )
            return False

    def get_repo_path(self, repository_id: str) -> Path | None:
        """Get the path to a cloned repository if it exists.

        Args:
            repository_id: Repository UUID string.

        Returns:
            Path to repository or None if not cloned.
        """
        repo_path = self._get_repo_path(repository_id)
        if repo_path.exists() and (repo_path / ".git").is_dir():
            return repo_path
        return None

    def _sanitize_error(self, error: str) -> str:
        """Remove potential credentials from error messages.

        Args:
            error: Raw error message.

        Returns:
            Sanitized error message.
        """
        # Remove tokens from URLs in error messages
        import re

        # Match patterns like https://token@github.com or https://user:pass@github.com
        sanitized = re.sub(
            r"(https?://)([^@\s]+)@",
            r"\1***@",
            error,
        )
        return sanitized


# Service singleton
_git_operations_service: GitOperationsService | None = None


def get_git_operations_service() -> GitOperationsService:
    """Get git operations service singleton."""
    global _git_operations_service
    if _git_operations_service is None:
        _git_operations_service = GitOperationsService()
    return _git_operations_service

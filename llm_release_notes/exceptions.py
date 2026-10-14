"""Custom exception classes for the Release Notes tool."""


class llmReleaseNotesError(Exception):
    """Base class for all application-specific errors."""

    pass


class GitError(llmReleaseNotesError):
    """Raised when a git command fails."""

    pass


class GitHubAPIError(llmReleaseNotesError):
    """Raised for errors related to the GitHub API."""

    pass


class LLMAPIError(llmReleaseNotesError):
    """Raised for errors related to the LLM API."""

    pass


class ConfigError(llmReleaseNotesError):
    """Raised for errors related to configuration."""

    pass

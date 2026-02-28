"""Platform adapters for GitHub, GitLab, etc."""

from __future__ import annotations

from jetsam.platforms.base import Platform


def get_platform(platform_name: str, cwd: str | None = None) -> Platform | None:
    """Factory to resolve the platform adapter by name.

    Args:
        platform_name: "github", "gitlab", or "unknown".
        cwd: Working directory for CLI commands.

    Returns:
        Platform instance or None if unsupported.
    """
    if platform_name == "github":
        from jetsam.platforms.github import GitHubPlatform
        return GitHubPlatform(cwd=cwd)
    if platform_name == "gitlab":
        from jetsam.platforms.gitlab import GitLabPlatform
        return GitLabPlatform(cwd=cwd)
    return None

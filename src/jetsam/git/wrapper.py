"""Git CLI wrapper with structured output."""

from __future__ import annotations

import asyncio
import subprocess
from dataclasses import dataclass, field


@dataclass
class GitResult:
    """Result of a git command execution."""

    returncode: int
    stdout: str
    stderr: str
    args: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def run_git_sync(
    args: list[str],
    cwd: str | None = None,
    check: bool = False,
) -> GitResult:
    """Run a git command synchronously."""
    cmd = ["git", *args]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=cwd,
        )
        result = GitResult(
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            args=args,
        )
        if check and not result.ok:
            raise GitError(result)
        return result
    except FileNotFoundError:
        return GitResult(returncode=127, stdout="", stderr="git: command not found", args=args)


async def run_git(
    args: list[str],
    cwd: str | None = None,
    check: bool = False,
) -> GitResult:
    """Run a git command asynchronously."""
    cmd = ["git", *args]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        stdout_bytes, stderr_bytes = await proc.communicate()
        result = GitResult(
            returncode=proc.returncode or 0,
            stdout=stdout_bytes.decode(),
            stderr=stderr_bytes.decode(),
            args=args,
        )
        if check and not result.ok:
            raise GitError(result)
        return result
    except FileNotFoundError:
        return GitResult(returncode=127, stdout="", stderr="git: command not found", args=args)


class GitError(Exception):
    """Raised when a git command fails and check=True."""

    def __init__(self, result: GitResult) -> None:
        self.result = result
        super().__init__(f"git {' '.join(result.args)} failed: {result.stderr.strip()}")

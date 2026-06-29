"""Configuration loading and management."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class JetsamConfig:
    """Jetsam configuration."""

    platform: str = "auto"  # auto | github | gitlab
    merge_strategy: str = "squash"  # squash | merge | rebase
    auto_push: bool = False
    ship_default: str = "pr"  # pr | merge
    pr_draft: bool = False
    branch_prefix: str = ""
    delete_on_merge: bool = True
    worktree: str = "auto"  # auto | always | never
    worktree_dir: str = ".worktrees"  # relative to repo root
    commit_message: str = "heuristic"  # heuristic | prompt | llm
    # Auto-stage (files=None) never sweeps these — agent/tool runtime churn that
    # is rarely an intentional commit. Globs (*.sqlite) or dir names (.kibitzer
    # matches anything under it). Has no effect when files are named explicitly.
    noise_paths: list[str] = field(
        default_factory=lambda: [
            ".jetsam", ".kibitzer", ".bird", ".riggs",
            "*.sqlite", "*.sqlite-wal", "*.sqlite-shm", "*.sqlite-journal",
        ]
    )

    # Runtime state (not from config file)
    config_path: str | None = field(default=None, repr=False)


def load_config(repo_root: str | None = None) -> JetsamConfig:
    """Load configuration from .jetsam/config.yaml and global config.

    Repo config overrides global config. Both are optional.
    """
    config = JetsamConfig()

    # Global config
    global_path = Path.home() / ".config" / "jetsam" / "config.yaml"
    if global_path.exists():
        _merge_from_file(config, global_path)

    # Repo config
    if repo_root:
        repo_path = Path(repo_root) / ".jetsam" / "config.yaml"
        if repo_path.exists():
            _merge_from_file(config, repo_path)
            config.config_path = str(repo_path)

    return config


def _merge_from_file(config: JetsamConfig, path: Path) -> None:
    """Merge values from a YAML file into the config."""
    try:
        with open(path) as f:
            data = yaml.safe_load(f)
    except (yaml.YAMLError, OSError):
        return

    if not isinstance(data, dict):
        return

    valid_fields = {f.name for f in config.__dataclass_fields__.values() if f.repr}
    for key, value in data.items():
        if key in valid_fields:
            setattr(config, key, value)


def valid_config_keys() -> set[str]:
    """Return the set of valid user-facing config keys."""
    return {f.name for f in JetsamConfig.__dataclass_fields__.values() if f.repr}


def global_config_path() -> Path:
    """Return the global config file path."""
    return Path.home() / ".config" / "jetsam" / "config.yaml"


def repo_config_path(repo_root: str) -> Path:
    """Return the repo config file path."""
    return Path(repo_root) / ".jetsam" / "config.yaml"


def save_config(config_path: str, key: str, value: str) -> None:
    """Write a single key to a YAML config file.

    Coerces string values to appropriate types (bool, str).
    """
    path = Path(config_path)
    data: dict[str, object] = {}
    if path.exists():
        try:
            with open(path) as f:
                loaded = yaml.safe_load(f)
            if isinstance(loaded, dict):
                data = loaded
        except (yaml.YAMLError, OSError):
            pass

    # Type coercion
    coerced: object = value
    if value.lower() in ("true", "yes"):
        coerced = True
    elif value.lower() in ("false", "no"):
        coerced = False

    data[key] = coerced
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False)

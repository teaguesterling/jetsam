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
    commit_message: str = "heuristic"  # heuristic | prompt | llm

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

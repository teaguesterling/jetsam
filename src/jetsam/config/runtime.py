"""In-memory runtime configuration for the MCP server.

Distinct from `jetsam.config.manager.JetsamConfig`, which is the file-backed
config loaded from `.jetsam/config.yaml`. This module holds *session* state
that the MCP `config()` tool reads and writes — wiped on server restart, no
disk persistence.

Env vars at launch seed the initial values (e.g. `JETSAM_ACTIVE_ROOT` set in
`.mcp.json` env block). Resetting reverts to those env-seeded values, not
hardcoded defaults.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, fields, replace
from typing import Any

_ENV_PREFIX = "JETSAM_"

_VALID_LOG_LEVELS = {"debug", "info", "warn", "warning", "error"}

# Canonical sync strategies — single source of truth shared by the CLI
# (click.Choice), the planner (plan_sync validation), and this runtime
# config, so the paths cannot drift (issue #19 follow-up audit).
SYNC_STRATEGIES: tuple[str, ...] = ("rebase", "merge")
_VALID_SYNC_STRATEGIES = set(SYNC_STRATEGIES)


@dataclass
class JetsamRuntimeConfig:
    """Session-scoped runtime knobs for the MCP server.

    Common keys (suite-wide convention):
        active_root: fallback when a workflow verb's `cwd=` arg is omitted.
            None means use the server's process cwd (today's behavior).
        log_level: debug | info | warn | error.

    Jetsam-specific:
        default_sync_strategy: rebase (today's default) | merge. Applies when
            sync() is called without an explicit strategy.
        default_base_branch: override for "main" — useful in repos that use
            "master" or "trunk" but haven't set the upstream tracking.
        signing_required: if True, save/ship/release fail fast when GPG isn't
            configured for the repo. Useful in fleet repos that require
            signed commits.
    """

    active_root: str | None = None
    log_level: str = "info"
    default_sync_strategy: str = "rebase"
    default_base_branch: str | None = None
    signing_required: bool = False

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> JetsamRuntimeConfig:
        """Build a config seeded from environment variables.

        Variables read (each optional):
            JETSAM_ACTIVE_ROOT         — path
            JETSAM_LOG_LEVEL           — debug/info/warn/error
            JETSAM_DEFAULT_SYNC_STRATEGY — rebase/merge
            JETSAM_DEFAULT_BASE_BRANCH — branch name
            JETSAM_SIGNING_REQUIRED    — true/false/1/0/yes/no

        Invalid values fall back to the dataclass default.
        """
        e = env if env is not None else os.environ
        cfg = cls()

        if v := e.get(f"{_ENV_PREFIX}ACTIVE_ROOT"):
            cfg.active_root = v
        v = e.get(f"{_ENV_PREFIX}LOG_LEVEL")
        if v and v.lower() in _VALID_LOG_LEVELS:
            cfg.log_level = v.lower()
        v = e.get(f"{_ENV_PREFIX}DEFAULT_SYNC_STRATEGY")
        if v and v.lower() in _VALID_SYNC_STRATEGIES:
            cfg.default_sync_strategy = v.lower()
        if v := e.get(f"{_ENV_PREFIX}DEFAULT_BASE_BRANCH"):
            cfg.default_base_branch = v
        if v := e.get(f"{_ENV_PREFIX}SIGNING_REQUIRED"):
            cfg.signing_required = _parse_bool(v)

        return cfg

    def to_dict(self) -> dict[str, Any]:
        """Flat dict for the MCP `config()` response."""
        return {f.name: getattr(self, f.name) for f in fields(self)}


def _parse_bool(s: str) -> bool:
    return s.strip().lower() in ("true", "1", "yes", "on")


# Module-level singleton, seeded from env on import.
_runtime: JetsamRuntimeConfig = JetsamRuntimeConfig.from_env()
_seed: JetsamRuntimeConfig = replace(_runtime)


def get_runtime() -> JetsamRuntimeConfig:
    """Return the current runtime config."""
    return _runtime


def update_runtime(values: dict[str, Any]) -> JetsamRuntimeConfig:
    """Merge values into the runtime config. Validates atomically.

    Raises ValueError on unknown keys or invalid values, leaving the runtime
    config unchanged.
    """
    valid_keys = {f.name for f in fields(JetsamRuntimeConfig)}
    unknown = set(values) - valid_keys
    if unknown:
        raise ValueError(
            f"unknown config key(s): {sorted(unknown)}. "
            f"Valid keys: {sorted(valid_keys)}"
        )

    global _runtime
    # Validate each value against the field's expected shape before applying.
    candidate = replace(_runtime)
    for key, value in values.items():
        _validate_one(key, value)
        setattr(candidate, key, value)

    _runtime = candidate
    return _runtime


def reset_runtime() -> JetsamRuntimeConfig:
    """Reset to the env-seeded values captured at module import time."""
    global _runtime
    _runtime = replace(_seed)
    return _runtime


def _validate_one(key: str, value: Any) -> None:
    """Per-key value validation."""
    if key == "log_level":
        if not isinstance(value, str) or value.lower() not in _VALID_LOG_LEVELS:
            raise ValueError(
                f"log_level must be one of {sorted(_VALID_LOG_LEVELS)}, got {value!r}"
            )
    elif key == "default_sync_strategy":
        if not isinstance(value, str) or value.lower() not in _VALID_SYNC_STRATEGIES:
            raise ValueError(
                f"default_sync_strategy must be one of "
                f"{sorted(_VALID_SYNC_STRATEGIES)}, got {value!r}"
            )
    elif key == "signing_required":
        if not isinstance(value, bool):
            raise ValueError(f"signing_required must be bool, got {type(value).__name__}")
    elif key in ("active_root", "default_base_branch"):
        if value is None or isinstance(value, str):
            return
        raise ValueError(f"{key} must be str or None, got {type(value).__name__}")

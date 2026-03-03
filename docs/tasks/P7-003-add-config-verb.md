# P7-003: Add Config Verb

**Phase:** 7 — CLI & Features
**Priority:** Low-medium impact, moderate effort
**Affects:** New file `src/jetsam/cli/verbs/config.py`, `src/jetsam/config/manager.py`

## Problem

The product spec lists a `config` management command for viewing and setting preferences.
Currently, users must manually edit `.jetsam/config.yaml` to change configuration.
There's no way to view the active (merged) configuration from the CLI.

## Solution

### `jetsam config` — View current configuration

```bash
$ jetsam config
  platform: auto (detected: github)
  merge_strategy: squash
  auto_push: false
  ship_default: pr
  pr_draft: false
  branch_prefix: ""
  delete_on_merge: true
  worktree: auto
  commit_message: heuristic

  Source: .jetsam/config.yaml
```

### `jetsam config <key>` — View a single value

```bash
$ jetsam config merge_strategy
squash
```

### `jetsam config <key> <value>` — Set a value

```bash
$ jetsam config merge_strategy rebase
  Set merge_strategy = rebase in .jetsam/config.yaml
```

### `jetsam config --global <key> <value>` — Set globally

```bash
$ jetsam config --global branch_prefix "teague/"
  Set branch_prefix = "teague/" in ~/.config/jetsam/config.yaml
```

### Implementation

1. Create `src/jetsam/cli/verbs/config.py`
2. Add `save_config()` function to `config/manager.py`
3. Register in `cli/main.py`

### Config writing function

```python
def save_config(config_path: str, key: str, value: Any) -> None:
    """Write a single key to a YAML config file."""
    path = Path(config_path)
    data = {}
    if path.exists():
        with open(path) as f:
            data = yaml.safe_load(f) or {}
    data[key] = value
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False)
```

### JSON mode

```bash
$ jetsam --json config
{"platform": "auto", "merge_strategy": "squash", ...}
```

## Acceptance Criteria

- [ ] `jetsam config` displays all active configuration
- [ ] `jetsam config <key>` displays a single value
- [ ] `jetsam config <key> <value>` writes to `.jetsam/config.yaml`
- [ ] `jetsam config --global <key> <value>` writes to `~/.config/jetsam/config.yaml`
- [ ] `--json` support for all config operations
- [ ] Config file is created if it doesn't exist
- [ ] Invalid keys are rejected with a helpful error
- [ ] Values are type-validated (bool, str, etc.)
- [ ] Tests for read, write, and validation

## Estimated Scope

~80-100 lines for the verb, ~20 lines for `save_config()`, ~30 lines of tests.

## Dependencies

- P6-001 (Wire config) — config verb is more useful when config actually affects behavior

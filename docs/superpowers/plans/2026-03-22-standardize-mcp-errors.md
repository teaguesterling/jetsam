# P6-002: Standardize MCP Error Returns — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Standardize all MCP tool error responses to use `JetsamError.to_dict()` so agents can detect errors uniformly via `if "error" in response`.

**Architecture:** Add two helper functions (`_no_platform_error`, `_no_pr_error`) to `tools.py`, then replace all ad-hoc error returns with `JetsamError.to_dict()` calls. Update the MCP server instruction string to document the error contract. TDD throughout.

**Tech Stack:** Python, pytest, FastMCP

**Spec:** `docs/superpowers/specs/2026-03-22-standardize-mcp-errors-design.md`

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `src/jetsam/mcp/tools.py` | Modify | Add helpers, replace all ad-hoc error returns |
| `src/jetsam/mcp/server.py` | Modify | Update instruction string |
| `tests/test_mcp_tools.py` | Modify | Add error-format tests |

---

### Task 1: Add helper functions and test infrastructure

**Files:**
- Modify: `src/jetsam/mcp/tools.py:30-36` (add helpers after `_plan_store`)
- Modify: `tests/test_mcp_tools.py` (add error-format test helpers)

- [ ] **Step 1: Write tests for helper functions**

Add a new test class at the end of `tests/test_mcp_tools.py`:

```python
class TestErrorHelpers:
    """Test the error helper functions produce standard JetsamError format."""

    def test_no_platform_error(self):
        from jetsam.mcp.tools import _no_platform_error

        result = _no_platform_error()
        assert result["error"] == "no_platform"
        assert "message" in result
        assert result["recoverable"] is False

    def test_no_pr_error(self):
        from jetsam.mcp.tools import _no_pr_error

        result = _no_pr_error("feature/foo")
        assert result["error"] == "no_pr"
        assert "feature/foo" in result["message"]
        assert result["recoverable"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_mcp_tools.py::TestErrorHelpers -v`
Expected: FAIL — `_no_platform_error` and `_no_pr_error` do not exist yet.

- [ ] **Step 3: Implement helpers**

Add after the `_get_store()` function (around line 44) in `src/jetsam/mcp/tools.py`:

```python
def _no_platform_error() -> dict[str, Any]:
    """Standard error for missing platform configuration."""
    return JetsamError(
        error="no_platform",
        message="No platform configured.",
        suggested_action="Configure a GitHub or GitLab remote.",
        recoverable=False,
    ).to_dict()


def _no_pr_error(branch: str) -> dict[str, Any]:
    """Standard error for missing PR."""
    return JetsamError(
        error="no_pr",
        message=f"No PR found for branch '{branch}'.",
        recoverable=True,
    ).to_dict()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_mcp_tools.py::TestErrorHelpers -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/jetsam/mcp/tools.py tests/test_mcp_tools.py
git commit -m "feat(mcp): add _no_platform_error and _no_pr_error helpers"
```

---

### Task 2: Standardize `log()` and `diff()` error returns

**Files:**
- Modify: `src/jetsam/mcp/tools.py:130-183` (`log` and `diff` functions)
- Modify: `tests/test_mcp_tools.py` (add error format tests)

- [ ] **Step 1: Write tests for log and diff error paths**

Add to `tests/test_mcp_tools.py`:

```python
class TestErrorFormats:
    """Verify all error paths return standard JetsamError dicts."""

    def test_log_error_returns_jetsam_error_dict(
        self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """log() should return a JetsamError dict, not a list, on error."""
        monkeypatch.setenv("GIT_DIR", str(tmp_git_repo / ".git"))
        monkeypatch.setenv("GIT_WORK_TREE", str(tmp_git_repo))

        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test")
        mcp_tools.register_tools(mcp)

        # Access the registered tool function
        log_fn = mcp._tool_manager._tools["log"].fn
        result = log_fn(n=10, branch="nonexistent-branch-xyz")

        assert isinstance(result, dict), "Error should be a dict, not a list"
        assert result["error"] == "git_error"
        assert "message" in result
        assert "recoverable" in result

    def test_diff_stat_error_returns_jetsam_error_dict(
        self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """diff() in stat mode should return JetsamError dict on error."""
        monkeypatch.setenv("GIT_DIR", str(tmp_git_repo / ".git"))
        monkeypatch.setenv("GIT_WORK_TREE", str(tmp_git_repo))

        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test")
        mcp_tools.register_tools(mcp)

        diff_fn = mcp._tool_manager._tools["diff"].fn
        result = diff_fn(target="nonexistent-ref-xyz", stat=True, staged=False)

        assert isinstance(result, dict)
        assert result["error"] == "git_error"
        assert "message" in result
        assert "recoverable" in result

    def test_diff_full_error_returns_jetsam_error_dict(
        self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """diff() in full mode should return JetsamError dict on error."""
        monkeypatch.setenv("GIT_DIR", str(tmp_git_repo / ".git"))
        monkeypatch.setenv("GIT_WORK_TREE", str(tmp_git_repo))

        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test")
        mcp_tools.register_tools(mcp)

        diff_fn = mcp._tool_manager._tools["diff"].fn
        result = diff_fn(target="nonexistent-ref-xyz", stat=False, staged=False)

        assert isinstance(result, dict)
        assert result["error"] == "git_error"
        assert "message" in result
        assert "recoverable" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_mcp_tools.py::TestErrorFormats -v`
Expected: FAIL — `log()` returns a list, `diff()` returns ad-hoc dicts.

- [ ] **Step 3: Update `log()` error return**

In `src/jetsam/mcp/tools.py`, change the `log()` error path (around line 143-144):

```python
# Before:
        if not result.ok:
            return [{"error": result.stderr.strip()}]

# After:
        if not result.ok:
            return JetsamError(
                error="git_error",
                message=result.stderr.strip(),
                recoverable=True,
            ).to_dict()
```

- [ ] **Step 4: Update `diff()` error returns**

In `src/jetsam/mcp/tools.py`, change both `diff()` error paths:

Stat mode (around line 170-171):
```python
# Before:
            if not result.ok:
                return {"error": result.stderr.strip()}

# After:
            if not result.ok:
                return JetsamError(
                    error="git_error",
                    message=result.stderr.strip(),
                    recoverable=True,
                ).to_dict()
```

Full mode (around line 182-183):
```python
# Before:
            result = run_git_sync(args)
            return {"diff": result.stdout, "ok": result.ok}

# After:
            result = run_git_sync(args)
            if not result.ok:
                return JetsamError(
                    error="git_error",
                    message=result.stderr.strip(),
                    recoverable=True,
                ).to_dict()
            return {"diff": result.stdout, "ok": result.ok}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_mcp_tools.py::TestErrorFormats -v`
Expected: PASS

- [ ] **Step 6: Run full test suite to check for regressions**

Run: `pytest tests/test_mcp_tools.py -v`
Expected: All tests PASS.

- [ ] **Step 7: Commit**

```bash
git add src/jetsam/mcp/tools.py tests/test_mcp_tools.py
git commit -m "feat(mcp): standardize log() and diff() error returns to JetsamError"
```

---

### Task 3: Standardize platform-dependent tool error returns

These tools all share the same `no_platform` / `no_pr` error patterns:
`pr_view`, `pr_list`, `pr_comment`, `pr_review`, `pr_comments`, `checks`, `issues`, `issue_close`.

**Files:**
- Modify: `src/jetsam/mcp/tools.py:200-427` (platform-dependent tools)
- Modify: `tests/test_mcp_tools.py` (add platform error tests)

- [ ] **Step 1: Write tests for no_platform errors**

Add to `TestErrorFormats` in `tests/test_mcp_tools.py`:

```python
    def test_pr_view_no_platform_returns_jetsam_error(
        self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("GIT_DIR", str(tmp_git_repo / ".git"))
        monkeypatch.setenv("GIT_WORK_TREE", str(tmp_git_repo))
        # No platform configured in tmp_git_repo
        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test")
        mcp_tools.register_tools(mcp)

        pr_view_fn = mcp._tool_manager._tools["pr_view"].fn
        result = pr_view_fn(branch=None)

        assert isinstance(result, dict)
        assert result["error"] == "no_platform"
        assert "message" in result
        assert "recoverable" in result

    def test_pr_list_no_platform_returns_jetsam_error_dict(
        self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """pr_list() should return a dict (not list) on error."""
        monkeypatch.setenv("GIT_DIR", str(tmp_git_repo / ".git"))
        monkeypatch.setenv("GIT_WORK_TREE", str(tmp_git_repo))

        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test")
        mcp_tools.register_tools(mcp)

        pr_list_fn = mcp._tool_manager._tools["pr_list"].fn
        result = pr_list_fn(state="open", author=None)

        assert isinstance(result, dict), "Error should be a dict, not a list"
        assert result["error"] == "no_platform"
        assert "message" in result
        assert "recoverable" in result

    def test_checks_no_platform_returns_jetsam_error_dict(
        self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("GIT_DIR", str(tmp_git_repo / ".git"))
        monkeypatch.setenv("GIT_WORK_TREE", str(tmp_git_repo))

        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test")
        mcp_tools.register_tools(mcp)

        checks_fn = mcp._tool_manager._tools["checks"].fn
        result = checks_fn(pr_number=None)

        assert isinstance(result, dict), "Error should be a dict, not a list"
        assert result["error"] == "no_platform"
        assert "message" in result

    def test_issues_no_platform_returns_jetsam_error_dict(
        self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("GIT_DIR", str(tmp_git_repo / ".git"))
        monkeypatch.setenv("GIT_WORK_TREE", str(tmp_git_repo))

        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test")
        mcp_tools.register_tools(mcp)

        issues_fn = mcp._tool_manager._tools["issues"].fn
        result = issues_fn(state="open", labels=None)

        assert isinstance(result, dict), "Error should be a dict, not a list"
        assert result["error"] == "no_platform"
        assert "message" in result

    def test_pr_comments_no_platform_returns_jetsam_error_dict(
        self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("GIT_DIR", str(tmp_git_repo / ".git"))
        monkeypatch.setenv("GIT_WORK_TREE", str(tmp_git_repo))

        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test")
        mcp_tools.register_tools(mcp)

        fn = mcp._tool_manager._tools["pr_comments"].fn
        result = fn(branch=None, pr_number=None)

        assert isinstance(result, dict), "Error should be a dict, not a list"
        assert result["error"] == "no_platform"
        assert "message" in result

    def test_pr_comment_no_platform_returns_jetsam_error(
        self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("GIT_DIR", str(tmp_git_repo / ".git"))
        monkeypatch.setenv("GIT_WORK_TREE", str(tmp_git_repo))

        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test")
        mcp_tools.register_tools(mcp)

        fn = mcp._tool_manager._tools["pr_comment"].fn
        result = fn(body="test", branch=None, pr_number=None)

        assert isinstance(result, dict)
        assert result["error"] == "no_platform"
        assert "message" in result

    def test_pr_review_no_platform_returns_jetsam_error(
        self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("GIT_DIR", str(tmp_git_repo / ".git"))
        monkeypatch.setenv("GIT_WORK_TREE", str(tmp_git_repo))

        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test")
        mcp_tools.register_tools(mcp)

        fn = mcp._tool_manager._tools["pr_review"].fn
        result = fn(event="approve", body="", branch=None, pr_number=None)

        assert isinstance(result, dict)
        assert result["error"] == "no_platform"
        assert "message" in result

    def test_issue_close_no_platform_returns_jetsam_error(
        self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("GIT_DIR", str(tmp_git_repo / ".git"))
        monkeypatch.setenv("GIT_WORK_TREE", str(tmp_git_repo))

        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test")
        mcp_tools.register_tools(mcp)

        fn = mcp._tool_manager._tools["issue_close"].fn
        result = fn(number=999, comment=None, reason="completed")

        assert isinstance(result, dict)
        assert result["error"] == "no_platform"
        assert "message" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_mcp_tools.py::TestErrorFormats -v -k "no_platform"`
Expected: FAIL — current code returns ad-hoc dicts or list-wrapped errors.

- [ ] **Step 3: Replace all `no_platform` error returns with `_no_platform_error()`**

In `src/jetsam/mcp/tools.py`, replace each `no_platform` error return:

`pr_view()` (around line 210):
```python
# Before:
        if platform is None:
            return {"error": "no_platform", "message": "No platform configured"}
# After:
        if platform is None:
            return _no_platform_error()
```

`pr_list()` (around line 230):
```python
# Before:
        if platform is None:
            return [{"error": "no_platform"}]
# After:
        if platform is None:
            return _no_platform_error()
```

`checks()` (around line 244):
```python
# Before:
        if platform is None:
            return [{"error": "no_platform"}]
# After:
        if platform is None:
            return _no_platform_error()
```

`issues()` (around line 340):
```python
# Before:
        if platform is None:
            return [{"error": "no_platform"}]
# After:
        if platform is None:
            return _no_platform_error()
```

`pr_comment()` (around line 360):
```python
# Before:
        if platform is None:
            return {"error": "no_platform", "message": "No platform configured"}
# After:
        if platform is None:
            return _no_platform_error()
```

`pr_review()` (around line 390):
```python
# Before:
        if platform is None:
            return {"error": "no_platform", "message": "No platform configured"}
# After:
        if platform is None:
            return _no_platform_error()
```

`pr_comments()` (around line 416):
```python
# Before:
        if platform is None:
            return [{"error": "no_platform"}]
# After:
        if platform is None:
            return _no_platform_error()
```

`issue_close()` (around line 444):
```python
# Before:
        if platform is None:
            return {"error": "no_platform", "message": "No platform configured"}
# After:
        if platform is None:
            return _no_platform_error()
```

- [ ] **Step 4: Replace all `no_pr` error returns with `_no_pr_error()`**

`checks()` (around line 250):
```python
# Before:
            if pr is None:
                return [{"error": "no_pr", "branch": repo_state.branch}]
# After:
            if pr is None:
                return _no_pr_error(repo_state.branch)
```

`pr_comment()` (around line 367):
```python
# Before:
            if pr is None:
                return {"error": "no_pr", "branch": actual_branch}
# After:
            if pr is None:
                return _no_pr_error(actual_branch)
```

`pr_review()` (around line 396):
```python
# Before:
            if pr is None:
                return {"error": "no_pr", "branch": actual_branch}
# After:
            if pr is None:
                return _no_pr_error(actual_branch)
```

`pr_comments()` (around line 423):
```python
# Before:
            if pr is None:
                return [{"error": "no_pr", "branch": actual_branch}]
# After:
            if pr is None:
                return _no_pr_error(actual_branch)
```

- [ ] **Step 5: Write test for `no_pr` error path with mocked platform**

Add to `TestErrorFormats` in `tests/test_mcp_tools.py`:

```python
    def test_checks_no_pr_returns_jetsam_error_dict(
        self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """checks() should return JetsamError dict when no PR exists."""
        monkeypatch.setenv("GIT_DIR", str(tmp_git_repo / ".git"))
        monkeypatch.setenv("GIT_WORK_TREE", str(tmp_git_repo))

        from unittest.mock import MagicMock

        from mcp.server.fastmcp import FastMCP

        # Mock platform that returns None for pr_for_branch
        mock_platform = MagicMock()
        mock_platform.pr_for_branch.return_value = None
        monkeypatch.setattr(mcp_tools, "_get_platform", lambda _: mock_platform)

        mcp = FastMCP("test")
        mcp_tools.register_tools(mcp)

        checks_fn = mcp._tool_manager._tools["checks"].fn
        result = checks_fn(pr_number=None)

        assert isinstance(result, dict), "Error should be a dict, not a list"
        assert result["error"] == "no_pr"
        assert "message" in result
        assert "recoverable" in result
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_mcp_tools.py::TestErrorFormats -v`
Expected: All PASS.

- [ ] **Step 7: Run full test suite**

Run: `pytest tests/test_mcp_tools.py -v`
Expected: All tests PASS.

- [ ] **Step 8: Commit**

```bash
git add src/jetsam/mcp/tools.py tests/test_mcp_tools.py
git commit -m "feat(mcp): standardize platform tool errors to JetsamError format"
```

---

### Task 4: Update MCP server instructions and final verification

**Files:**
- Modify: `src/jetsam/mcp/server.py:9-14`

- [ ] **Step 1: Update instruction string**

In `src/jetsam/mcp/server.py`, update the `instructions` parameter:

```python
# Before:
mcp = FastMCP("jetsam", instructions=(
    "jetsam is a git workflow accelerator. "
    "Use workflow tools (status, save, sync, log, diff) for common operations. "
    "Mutating tools (save, sync) return plans that must be confirmed with confirm(). "
    "Use the git tool for any git operation not covered by workflow tools."
))

# After:
mcp = FastMCP("jetsam", instructions=(
    "jetsam is a git workflow accelerator. "
    "Use workflow tools (status, save, sync, log, diff) for common operations. "
    "Mutating tools (save, sync) return plans that must be confirmed with confirm(). "
    "Use the git tool for any git operation not covered by workflow tools. "
    "Error responses always contain 'error' and 'message' keys. "
    "Check if 'error' in response to detect errors."
))
```

- [ ] **Step 2: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests PASS.

- [ ] **Step 3: Commit**

```bash
git add src/jetsam/mcp/server.py
git commit -m "docs(mcp): document error contract in server instruction string"
```

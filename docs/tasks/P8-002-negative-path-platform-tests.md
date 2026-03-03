# P8-002: Add Negative Path Tests for Platform Adapters

**Phase:** 8 — Testing & Polish
**Priority:** Medium impact, moderate effort
**Affects:** `tests/test_platform_github.py`, `tests/test_platform_gitlab.py`

## Problem

Current platform adapter tests are primarily happy-path: they verify correct parsing
of well-formed JSON responses. There are no tests for:

1. **Malformed JSON** from `gh`/`glab` (e.g., truncated output, HTML error pages)
2. **Missing fields** in JSON responses (e.g., API version changes)
3. **Network errors** (subprocess timeout, connection refused)
4. **Authentication failures** (expired token, revoked access)
5. **Rate limiting** (429 responses surfaced through CLI)
6. **Unexpected status codes** from platform CLIs
7. **Command not found** (gh/glab not installed)

The platform adapters have defensive coding (try/except, isinstance checks), but
these paths are untested.

## Solution

### Test categories to add:

#### 1. Command not found

```python
def test_gh_not_installed(self, monkeypatch):
    """GitHubPlatform handles missing gh gracefully."""
    # Mock subprocess.run to raise FileNotFoundError
    platform = GitHubPlatform()
    assert platform.is_available() is False
    assert platform.pr_for_branch("main") is None
```

#### 2. Malformed output

```python
def test_pr_view_html_error(self, monkeypatch):
    """Handle gh returning HTML error page instead of JSON."""
    # Mock gh to return HTML
    result = platform.pr_for_branch("main")
    assert result is None
```

#### 3. Missing fields

```python
def test_pr_parse_minimal_json(self):
    """Parse PR with only required fields present."""
    data = {"number": 1, "state": "open", "title": "test"}
    pr = _parse_pr(data)
    assert pr.number == 1
    assert pr.labels == []  # default
    assert pr.draft is False  # default
```

#### 4. Auth failure

```python
def test_pr_create_auth_failure(self, monkeypatch):
    """PlatformError raised when gh auth is expired."""
    # Mock gh to return auth error
    with pytest.raises(PlatformError, match="auth"):
        platform.pr_create(title="test")
```

#### 5. GitLab-specific edge cases

```python
def test_gitlab_mr_opened_vs_open(self):
    """GitLab returns 'opened' instead of 'open' - verify normalization."""

def test_gitlab_iid_vs_id(self):
    """GitLab uses iid (project-scoped) - verify correct field extraction."""
```

## Acceptance Criteria

- [ ] Tests for `gh`/`glab` not installed (FileNotFoundError)
- [ ] Tests for malformed JSON output (JSONDecodeError)
- [ ] Tests for missing/extra fields in API responses
- [ ] Tests for PlatformError propagation from pr_create/release_create
- [ ] Tests for `is_available()` failure modes
- [ ] Tests for GitLab state normalization edge cases
- [ ] All new tests use mocking (no real gh/glab calls)

## Estimated Scope

~20-30 new tests, ~150-200 lines across the two platform test files.

## Dependencies

- P5-002 (Consolidate PlatformError) — tests should import from base.py

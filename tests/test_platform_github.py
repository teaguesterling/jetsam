"""Tests for GitHub platform adapter.

These tests mock the gh CLI to avoid requiring authentication.
"""

from unittest.mock import patch

from jetsam.platforms.github import GitHubPlatform, _normalize_check_status, _parse_pr


class TestParsepr:
    def test_basic(self):
        data = {
            "number": 42,
            "state": "OPEN",
            "title": "Fix parser",
            "body": "Fixes the parser bug",
            "url": "https://github.com/user/repo/pull/42",
            "baseRefName": "main",
            "headRefName": "fix-parser",
            "isDraft": False,
            "labels": [{"name": "bug"}],
        }
        pr = _parse_pr(data)
        assert pr.number == 42
        assert pr.state == "open"
        assert pr.title == "Fix parser"
        assert pr.base == "main"
        assert pr.labels == ["bug"]

    def test_empty_labels(self):
        data = {"number": 1, "state": "open", "labels": []}
        pr = _parse_pr(data)
        assert pr.labels == []


class TestNormalizeCheckStatus:
    def test_pass(self):
        assert _normalize_check_status("SUCCESS") == "pass"
        assert _normalize_check_status("pass") == "pass"

    def test_fail(self):
        assert _normalize_check_status("FAILURE") == "fail"
        assert _normalize_check_status("error") == "fail"

    def test_pending(self):
        assert _normalize_check_status("PENDING") == "pending"
        assert _normalize_check_status("in_progress") == "pending"

    def test_neutral(self):
        assert _normalize_check_status("neutral") == "neutral"
        assert _normalize_check_status("skipped") == "neutral"


class TestGitHubPlatform:
    def test_pr_for_branch_not_found(self):
        """When gh returns an error, pr_for_branch returns None."""
        platform = GitHubPlatform()
        with patch.object(platform, "_run_gh_json", return_value=(False, "no PR")):
            result = platform.pr_for_branch("no-pr-branch")
            assert result is None

    def test_pr_for_branch_found(self):
        platform = GitHubPlatform()
        mock_data = {
            "number": 10,
            "state": "OPEN",
            "title": "Feature",
            "body": "",
            "url": "https://github.com/u/r/pull/10",
            "baseRefName": "main",
            "headRefName": "feature",
            "isDraft": False,
            "labels": [],
        }
        with patch.object(platform, "_run_gh_json", return_value=(True, mock_data)):
            pr = platform.pr_for_branch("feature")
            assert pr is not None
            assert pr.number == 10

    def test_pr_list_empty(self):
        platform = GitHubPlatform()
        with patch.object(platform, "_run_gh_json", return_value=(True, [])):
            prs = platform.pr_list()
            assert prs == []

    def test_pr_list(self):
        platform = GitHubPlatform()
        mock_data = [
            {"number": 1, "state": "open", "title": "PR 1", "url": "", "baseRefName": "main",
             "headRefName": "a", "isDraft": False, "labels": []},
            {"number": 2, "state": "open", "title": "PR 2", "url": "", "baseRefName": "main",
             "headRefName": "b", "isDraft": True, "labels": []},
        ]
        with patch.object(platform, "_run_gh_json", return_value=(True, mock_data)):
            prs = platform.pr_list()
            assert len(prs) == 2
            assert prs[1].draft is True

    def test_pr_checks(self):
        platform = GitHubPlatform()
        mock_data = [
            {"name": "CI", "state": "SUCCESS", "detailsUrl": "https://ci.example.com"},
            {"name": "Lint", "state": "FAILURE", "detailsUrl": ""},
        ]
        with patch.object(platform, "_run_gh_json", return_value=(True, mock_data)):
            checks = platform.pr_checks(42)
            assert len(checks) == 2
            assert checks[0].status == "pass"
            assert checks[1].status == "fail"

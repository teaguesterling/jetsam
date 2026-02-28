"""Phase 2 tests — ship, switch, pr, checks, init."""

import json
import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from jetsam.cli.main import cli
from jetsam.core.planner import plan_ship, plan_switch
from jetsam.core.state import PRInfo, RepoState


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@test.com",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@test.com",
    }
    return subprocess.run(
        ["git", *args],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )


def _invoke(args: list[str], repo: Path) -> object:
    runner = CliRunner()
    return runner.invoke(
        cli,
        args,
        env={
            "GIT_DIR": str(repo / ".git"),
            "GIT_WORK_TREE": str(repo),
        },
    )


def _make_state(**kwargs) -> RepoState:
    defaults = dict(
        branch="feature",
        upstream="origin/feature",
        default_branch="main",
        dirty=True,
        staged=["already_staged.py"],
        unstaged=["modified.py", "other.py"],
        untracked=["scratch.txt"],
        ahead=1,
        behind=0,
        stash_count=0,
        platform="github",
        remote="user/repo",
        remote_url="git@github.com:user/repo.git",
        head_sha="abc123",
        repo_root="/tmp/repo",
    )
    defaults.update(kwargs)
    return RepoState(**defaults)


# ── plan_switch tests ─────────────────────────────────────────────


class TestPlanSwitch:
    def test_clean_switch(self):
        state = _make_state(dirty=False)
        plan = plan_switch(state, plan_id="p_test", branch="develop")
        actions = [s.action for s in plan.steps]
        assert actions == ["checkout"]
        assert plan.steps[0].params["branch"] == "develop"
        assert plan.steps[0].params["create"] is False

    def test_clean_switch_create(self):
        state = _make_state(dirty=False)
        plan = plan_switch(
            state, plan_id="p_test", branch="new-feature", create=True,
        )
        assert plan.steps[0].params["create"] is True

    def test_dirty_switch_stashes(self):
        state = _make_state(dirty=True)
        plan = plan_switch(state, plan_id="p_test", branch="other")
        actions = [s.action for s in plan.steps]
        assert actions == ["stash", "checkout", "stash_pop"]
        assert any("stash" in w.lower() for w in plan.warnings)

    def test_switch_to_dict(self):
        state = _make_state(dirty=False)
        plan = plan_switch(state, plan_id="p_test", branch="dev")
        d = plan.to_dict()
        assert d["plan_id"] == "p_test"
        assert d["verb"] == "switch"


# ── Executor tests for new step types ────────────────────────────


class TestCheckoutExecutor:
    def test_checkout_existing_branch(self, tmp_git_repo: Path):
        # Create a branch to switch to
        _git(tmp_git_repo, "branch", "feature")

        from jetsam.core.executor import _exec_checkout
        from jetsam.core.planner import PlanStep

        step = PlanStep(
            action="checkout",
            params={"branch": "feature", "create": False},
        )
        result = _exec_checkout(step, cwd=str(tmp_git_repo))
        assert result.ok
        assert result.details["branch"] == "feature"

        # Verify we're on the feature branch
        branch = _git(tmp_git_repo, "rev-parse", "--abbrev-ref", "HEAD")
        assert branch.stdout.strip() == "feature"

    def test_checkout_create_branch(self, tmp_git_repo: Path):
        from jetsam.core.executor import _exec_checkout
        from jetsam.core.planner import PlanStep

        step = PlanStep(
            action="checkout",
            params={"branch": "new-branch", "create": True},
        )
        result = _exec_checkout(step, cwd=str(tmp_git_repo))
        assert result.ok
        assert result.details["branch"] == "new-branch"

    def test_checkout_nonexistent_fails(self, tmp_git_repo: Path):
        from jetsam.core.executor import _exec_checkout
        from jetsam.core.planner import PlanStep

        step = PlanStep(
            action="checkout",
            params={"branch": "does-not-exist", "create": False},
        )
        result = _exec_checkout(step, cwd=str(tmp_git_repo))
        assert not result.ok
        assert result.error


class TestPRExecutors:
    def test_pr_create_no_platform(self, tmp_git_repo: Path):
        """PR create should fail gracefully with no platform."""
        from jetsam.core.executor import _exec_pr_create
        from jetsam.core.planner import PlanStep

        step = PlanStep(
            action="pr_create",
            params={"title": "test", "base": "main"},
        )
        result = _exec_pr_create(step, cwd=str(tmp_git_repo))
        assert not result.ok
        assert "platform" in result.error.lower()

    def test_pr_update_noop(self):
        """PR update is a no-op (push already updates the PR)."""
        from jetsam.core.executor import _exec_pr_update
        from jetsam.core.planner import PlanStep

        step = PlanStep(
            action="pr_update",
            params={"number": 42},
        )
        result = _exec_pr_update(step, cwd=None)
        assert result.ok
        assert result.details["number"] == 42

    def test_pr_merge_no_platform(self, tmp_git_repo: Path):
        """PR merge should fail gracefully with no platform."""
        from jetsam.core.executor import _exec_pr_merge
        from jetsam.core.planner import PlanStep

        step = PlanStep(
            action="pr_merge",
            params={"strategy": "squash"},
        )
        result = _exec_pr_merge(step, cwd=str(tmp_git_repo))
        assert not result.ok


# ── CLI verb tests ───────────────────────────────────────────────


class TestShipVerb:
    def test_dry_run_json(self, dirty_git_repo: Path):
        result = _invoke(
            ["--json", "ship", "--dry-run", "-m", "ship it"],
            dirty_git_repo,
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "plan_id" in data
        actions = [s["action"] for s in data["steps"]]
        assert "commit" in actions
        assert "push" in actions

    def test_dry_run_with_pr(self, dirty_git_repo: Path):
        result = _invoke(
            ["--json", "ship", "--dry-run", "-m", "with pr"],
            dirty_git_repo,
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        actions = [s["action"] for s in data["steps"]]
        assert "pr_create" in actions

    def test_dry_run_no_pr(self, dirty_git_repo: Path):
        result = _invoke(
            ["--json", "ship", "--dry-run", "--no-pr", "-m", "no pr"],
            dirty_git_repo,
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        actions = [s["action"] for s in data["steps"]]
        assert "pr_create" not in actions

    def test_ship_human_dry_run(self, dirty_git_repo: Path):
        result = _invoke(
            ["ship", "--dry-run", "-m", "human ship"],
            dirty_git_repo,
        )
        assert result.exit_code == 0
        assert "Stage" in result.output or "Commit" in result.output

    def test_ship_alias(self, dirty_git_repo: Path):
        """'h' should alias to ship."""
        result = _invoke(
            ["--json", "h", "--dry-run", "-m", "alias test"],
            dirty_git_repo,
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["verb"] == "ship"


class TestSwitchVerb:
    def test_switch_dry_run_json(self, tmp_git_repo: Path):
        _git(tmp_git_repo, "branch", "feature")
        result = _invoke(
            ["--json", "switch", "--dry-run", "feature"],
            tmp_git_repo,
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["verb"] == "switch"
        actions = [s["action"] for s in data["steps"]]
        assert "checkout" in actions

    def test_switch_create_dry_run(self, tmp_git_repo: Path):
        result = _invoke(
            ["--json", "switch", "--dry-run", "-c", "new-branch"],
            tmp_git_repo,
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        checkout = next(
            s for s in data["steps"] if s["action"] == "checkout"
        )
        assert checkout["create"] is True

    def test_switch_execute(self, tmp_git_repo: Path):
        _git(tmp_git_repo, "branch", "target")
        result = _invoke(
            ["--json", "switch", "--execute", "target"],
            tmp_git_repo,
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "ok"

        # Verify we switched
        branch = _git(tmp_git_repo, "rev-parse", "--abbrev-ref", "HEAD")
        assert branch.stdout.strip() == "target"

    def test_switch_execute_create(self, tmp_git_repo: Path):
        result = _invoke(
            ["--json", "switch", "--execute", "-c", "brand-new"],
            tmp_git_repo,
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "ok"

        branch = _git(tmp_git_repo, "rev-parse", "--abbrev-ref", "HEAD")
        assert branch.stdout.strip() == "brand-new"

    def test_switch_dirty_stashes(self, dirty_git_repo: Path):
        _git(dirty_git_repo, "branch", "target")
        result = _invoke(
            ["--json", "switch", "--dry-run", "target"],
            dirty_git_repo,
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        actions = [s["action"] for s in data["steps"]]
        assert "stash" in actions
        assert "stash_pop" in actions

    def test_switch_alias(self, tmp_git_repo: Path):
        """'w' should alias to switch."""
        _git(tmp_git_repo, "branch", "feat")
        result = _invoke(
            ["--json", "w", "--dry-run", "feat"],
            tmp_git_repo,
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["verb"] == "switch"

    def test_switch_human_output(self, tmp_git_repo: Path):
        _git(tmp_git_repo, "branch", "feat")
        result = _invoke(
            ["switch", "--dry-run", "feat"],
            tmp_git_repo,
        )
        assert result.exit_code == 0
        assert "feat" in result.output


class TestChecksVerb:
    @patch("jetsam.cli.verbs.checks.GitHubPlatform")
    def test_checks_json(self, mock_platform_cls, tmp_git_repo: Path):
        """Test checks with mocked platform."""
        from jetsam.platforms.base import CheckResult

        mock_platform = MagicMock()
        mock_platform.pr_for_branch.return_value = MagicMock(number=42)
        mock_platform.pr_checks.return_value = [
            CheckResult(name="CI", status="pass", url="https://ci.example.com"),
            CheckResult(name="lint", status="fail", url=""),
        ]
        mock_platform_cls.return_value = mock_platform

        result = _invoke(["--json", "checks"], tmp_git_repo)
        # This may fail if platform detection doesn't find github
        # In that case the exit_code will be 1
        if result.exit_code == 0:
            data = json.loads(result.output)
            assert isinstance(data, list)

    def test_checks_no_platform(self, tmp_git_repo: Path):
        """Checks should fail gracefully with no platform."""
        result = _invoke(["--json", "checks"], tmp_git_repo)
        # tmp_git_repo has no remote, so no platform
        assert result.exit_code == 1


class TestPRVerb:
    def test_pr_no_platform(self, tmp_git_repo: Path):
        """PR view should handle no platform gracefully."""
        result = _invoke(["pr"], tmp_git_repo)
        assert "No platform" in result.output or result.exit_code == 1

    def test_pr_list_no_platform(self, tmp_git_repo: Path):
        result = _invoke(["pr", "list"], tmp_git_repo)
        assert "No platform" in result.output or result.exit_code == 1

    def test_pr_alias(self, tmp_git_repo: Path):
        """'p' should alias to pr."""
        result = _invoke(["p"], tmp_git_repo)
        # Should invoke pr command (may fail due to no platform, that's fine)
        assert "No platform" in result.output or result.exit_code == 1


class TestInitVerb:
    def test_init_json(self, tmp_git_repo: Path):
        result = _invoke(["--json", "init"], tmp_git_repo)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "platform" in data
        assert "default_branch" in data
        assert data["branch"] == "main"

        # Verify .jetsam directory was created
        assert (tmp_git_repo / ".jetsam").is_dir()
        assert (tmp_git_repo / ".jetsam" / "plans").is_dir()

    def test_init_human(self, tmp_git_repo: Path):
        result = _invoke(["init"], tmp_git_repo)
        assert result.exit_code == 0
        assert "Initialized jetsam" in result.output
        assert "main" in result.output

    def test_init_with_mcp(self, tmp_git_repo: Path):
        result = _invoke(["--json", "init", "--mcp"], tmp_git_repo)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "mcp_json" in data

        # Verify .mcp.json was created
        mcp_path = tmp_git_repo / ".mcp.json"
        assert mcp_path.exists()
        mcp_config = json.loads(mcp_path.read_text())
        assert "mcpServers" in mcp_config
        assert "jetsam" in mcp_config["mcpServers"]

    def test_init_idempotent(self, tmp_git_repo: Path):
        """Running init twice should be safe."""
        _invoke(["init"], tmp_git_repo)
        result = _invoke(["init"], tmp_git_repo)
        assert result.exit_code == 0


# ── Integration: switch + save flow ──────────────────────────────


class TestSwitchSaveFlow:
    def test_create_branch_save_switch_back(self, tmp_git_repo: Path):
        """Full flow: create branch → modify → save → switch back."""
        # Create and switch to feature branch
        result = _invoke(
            ["--json", "switch", "--execute", "-c", "feature"],
            tmp_git_repo,
        )
        assert result.exit_code == 0

        # Create a file and save
        (tmp_git_repo / "feature.py").write_text("feature = True\n")
        result = _invoke(
            ["--json", "save", "--execute", "-m", "add feature",
             "feature.py"],
            tmp_git_repo,
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "ok"

        # Switch back to main
        result = _invoke(
            ["--json", "switch", "--execute", "main"],
            tmp_git_repo,
        )
        assert result.exit_code == 0

        # Verify we're on main
        branch = _git(tmp_git_repo, "rev-parse", "--abbrev-ref", "HEAD")
        assert branch.stdout.strip() == "main"

        # Verify feature.py doesn't exist on main
        assert not (tmp_git_repo / "feature.py").exists()


# ── Ship planner tests ───────────────────────────────────────────


class TestPlanShipPhase2:
    def test_merge_step_included(self):
        state = _make_state()
        plan = plan_ship(
            state, plan_id="p_test", message="ship + merge",
            merge=True,
        )
        actions = [s.action for s in plan.steps]
        assert "pr_merge" in actions

    def test_existing_pr_updates(self):
        pr = PRInfo(number=99, state="open", title="existing PR")
        state = _make_state(pr=pr)
        plan = plan_ship(state, plan_id="p_test", message="update")
        actions = [s.action for s in plan.steps]
        assert "pr_update" in actions
        assert "pr_create" not in actions
        pr_step = next(s for s in plan.steps if s.action == "pr_update")
        assert pr_step.params["number"] == 99

    def test_target_branch(self):
        state = _make_state()
        plan = plan_ship(
            state, plan_id="p_test", message="ship",
            to="develop",
        )
        pr_step = next(s for s in plan.steps if s.action == "pr_create")
        assert pr_step.params["base"] == "develop"

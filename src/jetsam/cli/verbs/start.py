"""start verb — begin work on an issue or feature branch."""

import click

from jetsam.core.executor import execute_plan
from jetsam.core.output import format_json
from jetsam.core.planner import Plan, plan_start
from jetsam.core.plans import generate_plan_id
from jetsam.core.state import build_state


@click.command()
@click.argument("target")
@click.option("-w", "--worktree", is_flag=True, help="Create a worktree instead of switching")
@click.option("--base", default=None, help="Base branch (default: main/master)")
@click.option("--prefix", default="", help="Branch name prefix (e.g. feature/)")
@click.option("--dry-run", is_flag=True, help="Show plan without executing")
@click.option("--execute", "auto_execute", is_flag=True, help="Execute without prompting")
@click.pass_context
def start(
    ctx: click.Context,
    target: str,
    worktree: bool,
    base: str | None,
    prefix: str,
    dry_run: bool,
    auto_execute: bool,
) -> None:
    """Start work on an issue or feature.

    TARGET is an issue number (e.g. 42) or branch name (e.g. fix-parser).
    If numeric, the issue title is used to generate a branch name slug.
    """
    state = build_state()
    plan_id = generate_plan_id()

    # If target is numeric, try to fetch issue title for slug
    issue_title = None
    if target.isdigit():
        issue_title = _fetch_issue_title(state, int(target))

    plan = plan_start(
        state,
        plan_id=plan_id,
        target=target,
        issue_title=issue_title,
        branch_prefix=prefix,
        worktree=worktree,
        base=base,
    )

    json_mode = ctx.obj.get("json")

    if dry_run:
        if json_mode:
            click.echo(format_json(plan.to_dict()))
        else:
            _show_plan_human(plan)
        return

    if not auto_execute and not json_mode:
        _show_plan_human(plan)
        if plan.warnings:
            for w in plan.warnings:
                click.echo(f"  \u26a0 {w}")

        choice = click.prompt(
            "  [c]onfirm / [a]bort",
            type=click.Choice(["c", "a"]),
            default="c",
        )
        if choice == "a":
            click.echo("  Aborted.")
            return

    result = execute_plan(plan)

    if json_mode:
        click.echo(format_json(result.to_dict()))
    else:
        for step_result in result.results:
            symbol = "\u2713" if step_result.ok else "\u2717"
            msg = step_result.step
            if step_result.step == "checkout":
                msg = f"Created branch {step_result.details.get('branch', '')}"
            elif step_result.step == "worktree_add":
                path = step_result.details.get("path", "")
                branch = step_result.details.get("branch", "")
                msg = f"Created worktree {branch} at {path}"
            elif step_result.step == "stash":
                msg = "Stashed dirty changes"
            elif step_result.step == "stash_pop":
                msg = "Restored stashed changes"
            if step_result.error:
                msg = f"{step_result.step}: {step_result.error}"
            click.echo(f"  {symbol} {msg}")

        if result.status != "ok":
            ctx.exit(1)


def _fetch_issue_title(state: object, number: int) -> str | None:
    """Try to fetch issue title from the platform."""
    from jetsam.platforms import get_platform

    platform_name = getattr(state, "platform", "unknown")
    cwd = getattr(state, "repo_root", None)
    platform = get_platform(platform_name, cwd=cwd)
    if platform is None:
        return None

    issue = platform.issue_get(number)
    return issue.title if issue else None


def _show_plan_human(plan: Plan) -> None:
    branch = plan.params.get("branch", "")
    base = plan.params.get("base", "")
    is_worktree = plan.params.get("worktree", False)
    mode = "worktree" if is_worktree else "branch"

    click.echo(f"\n  Start: {branch} ({mode} from {base})")
    click.echo("  " + "\u2500" * 30)
    for step in plan.steps:
        if step.action == "stash":
            click.echo("  Stash: auto-save dirty changes")
        elif step.action == "checkout":
            click.echo(f"  Checkout: {step.params.get('branch', '')} (new)")
        elif step.action == "worktree_add":
            click.echo(f"  Worktree: create {step.params.get('branch', '')}")
        elif step.action == "stash_pop":
            click.echo("  Stash: restore changes")
    click.echo()

"""finish verb — merge PR, clean up branch."""

import click

from jetsam.core.executor import execute_plan
from jetsam.core.output import format_json
from jetsam.core.planner import Plan, plan_finish
from jetsam.core.plans import generate_plan_id
from jetsam.core.state import build_state


@click.command()
@click.option("--strategy", type=click.Choice(["squash", "merge", "rebase"]),
              default="squash", help="Merge strategy (default: squash)")
@click.option("--no-delete", is_flag=True, help="Keep the branch after merging")
@click.option("--dry-run", is_flag=True, help="Show plan without executing")
@click.option("--execute", "auto_execute", is_flag=True, help="Execute without prompting")
@click.pass_context
def finish(
    ctx: click.Context,
    strategy: str,
    no_delete: bool,
    dry_run: bool,
    auto_execute: bool,
) -> None:
    """Merge PR and clean up the current branch.

    Merges the PR for the current branch, switches to the default branch,
    and deletes the feature branch.
    """
    state = build_state()
    plan_id = generate_plan_id()

    # Detect worktree path if applicable
    worktree_path = None
    if state.worktree and state.worktree.active:
        worktree_path = state.worktree.current

    plan = plan_finish(
        state,
        plan_id=plan_id,
        strategy=strategy,
        no_delete=no_delete,
        worktree_path=worktree_path,
    )

    json_mode = ctx.obj.get("json")

    if not plan.steps:
        if json_mode:
            click.echo(format_json(plan.to_dict()))
        else:
            for w in plan.warnings:
                click.echo(f"  \u26a0 {w}")
        return

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
            if step_result.step == "pr_merge":
                num = step_result.details.get("number", "")
                strat = step_result.details.get("strategy", "")
                msg = f"PR #{num} merged ({strat})"
            elif step_result.step == "checkout":
                msg = f"Switched to {step_result.details.get('branch', '')}"
            elif step_result.step == "fetch":
                msg = "Fetched latest refs"
            elif step_result.step == "branch_delete":
                msg = f"Deleted branch {step_result.details.get('branch', '')}"
            elif step_result.step == "worktree_remove":
                msg = f"Removed worktree {step_result.details.get('path', '')}"
            if step_result.error:
                msg = f"{step_result.step}: {step_result.error}"
            click.echo(f"  {symbol} {msg}")

        if result.status != "ok":
            ctx.exit(1)


def _show_plan_human(plan: Plan) -> None:
    branch = plan.params.get("branch", "")
    strategy = plan.params.get("strategy", "squash")

    click.echo(f"\n  Finish: {branch} ({strategy})")
    click.echo("  " + "\u2500" * 30)
    for step in plan.steps:
        if step.action == "pr_merge":
            num = step.params.get("number", "?")
            click.echo(f"  Merge: PR #{num} ({strategy})")
        elif step.action == "checkout":
            click.echo(f"  Checkout: {step.params.get('branch', '')}")
        elif step.action == "fetch":
            click.echo("  Fetch: update refs")
        elif step.action == "branch_delete":
            click.echo(f"  Delete: branch {step.params.get('branch', '')}")
        elif step.action == "worktree_remove":
            click.echo(f"  Remove: worktree {step.params.get('path', '')}")
    click.echo()

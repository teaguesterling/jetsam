"""tidy verb — prune merged branches and stale remotes."""

import click

from jetsam.core.executor import execute_plan
from jetsam.core.output import format_json
from jetsam.core.planner import Plan, plan_tidy
from jetsam.core.plans import generate_plan_id
from jetsam.core.state import build_state


@click.command()
@click.option("--dry-run", is_flag=True, help="Show plan without executing")
@click.option("--execute", "auto_execute", is_flag=True, help="Execute without prompting")
@click.pass_context
def tidy(
    ctx: click.Context,
    dry_run: bool,
    auto_execute: bool,
) -> None:
    """Clean up merged branches and stale remote refs.

    Prunes remote-tracking branches that no longer exist on the server,
    deletes local branches whose upstream is gone, and prunes stale
    worktree references.
    """
    state = build_state()
    plan_id = generate_plan_id()

    plan = plan_tidy(state, plan_id=plan_id)

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
            if step_result.step == "remote_prune":
                remote = step_result.details.get("remote", "origin")
                msg = f"Pruned stale refs from {remote}"
            elif step_result.step == "prune_merged_branches":
                pruned = step_result.details.get("pruned", [])
                count = step_result.details.get("count", 0)
                if count:
                    msg = f"Deleted {count} merged branches: {', '.join(pruned)}"
                else:
                    msg = "No merged branches to prune"
            elif step_result.step == "worktree_prune":
                msg = "Pruned stale worktree refs"
            if step_result.error:
                msg = f"{step_result.step}: {step_result.error}"
            click.echo(f"  {symbol} {msg}")

        if result.status != "ok":
            ctx.exit(1)


def _show_plan_human(plan: Plan) -> None:
    click.echo("\n  Tidy: clean up branches and refs")
    click.echo("  " + "\u2500" * 30)
    for step in plan.steps:
        if step.action == "remote_prune":
            click.echo(f"  Prune: stale remote refs ({step.params.get('remote', 'origin')})")
        elif step.action == "prune_merged_branches":
            click.echo("  Prune: local branches with gone upstream")
        elif step.action == "worktree_prune":
            click.echo("  Prune: stale worktree refs")
    click.echo()

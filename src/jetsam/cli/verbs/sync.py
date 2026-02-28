"""sync verb — pull/rebase from upstream, push local."""

import click

from jetsam.core.executor import execute_plan
from jetsam.core.output import format_json
from jetsam.core.planner import Plan, plan_sync
from jetsam.core.plans import generate_plan_id
from jetsam.core.state import build_state


@click.command()
@click.option("--strategy", type=click.Choice(["rebase", "merge"]), default=None,
              help="Sync strategy (default: rebase for feature, merge for default)")
@click.option("--dry-run", is_flag=True, help="Show plan without executing")
@click.option("--execute", "auto_execute", is_flag=True, help="Execute without prompting")
@click.pass_context
def sync(
    ctx: click.Context,
    strategy: str | None,
    dry_run: bool,
    auto_execute: bool,
) -> None:
    """Pull/rebase from upstream, push local."""
    state = build_state()
    plan_id = generate_plan_id()

    plan = plan_sync(state, plan_id=plan_id, strategy=strategy)

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

        choice = click.prompt("  [c]onfirm / [a]bort", type=click.Choice(["c", "a"]), default="c")
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
            if step_result.error:
                msg = f"{step_result.step}: {step_result.error}"
            click.echo(f"  {symbol} {msg}")

        if result.status != "ok":
            ctx.exit(1)


def _show_plan_human(plan: Plan) -> None:
    click.echo(f"\n  Sync: {plan.verb}")
    click.echo("  " + "\u2500" * 30)
    for step in plan.steps:
        if step.action == "fetch":
            click.echo(f"  Fetch: {step.params.get('remote', 'origin')}")
        elif step.action == "rebase":
            click.echo(f"  Rebase: onto {step.params.get('onto', '')}")
        elif step.action == "merge":
            click.echo(f"  Merge: from {step.params.get('from', '')}")
        elif step.action == "push":
            remote = step.params.get("remote", "origin")
            branch = step.params.get("branch", "")
            click.echo(f"  Push: {remote}/{branch}")
        elif step.action == "stash":
            click.echo("  Stash: auto-save dirty changes")
        elif step.action == "stash_pop":
            click.echo("  Stash: restore changes")
    click.echo()

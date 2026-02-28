"""switch verb — stash-aware branch switching."""

import click

from jetsam.core.executor import execute_plan
from jetsam.core.output import format_json
from jetsam.core.planner import Plan, plan_switch
from jetsam.core.plans import generate_plan_id
from jetsam.core.state import build_state


@click.command()
@click.argument("branch")
@click.option("-c", "--create", is_flag=True, help="Create the branch if it doesn't exist")
@click.option("--dry-run", is_flag=True, help="Show plan without executing")
@click.option("--execute", "auto_execute", is_flag=True, help="Execute without prompting")
@click.pass_context
def switch(
    ctx: click.Context,
    branch: str,
    create: bool,
    dry_run: bool,
    auto_execute: bool,
) -> None:
    """Switch branches with automatic stash/unstash.

    BRANCH is the target branch to switch to.
    """
    state = build_state()
    plan_id = generate_plan_id()

    plan = plan_switch(state, plan_id=plan_id, branch=branch, create=create)

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
                msg = f"Switched to {step_result.details.get('branch', '')}"
            elif step_result.step == "stash":
                msg = "Stashed dirty changes"
            elif step_result.step == "stash_pop":
                msg = "Restored stashed changes"
            if step_result.error:
                msg = f"{step_result.step}: {step_result.error}"
            click.echo(f"  {symbol} {msg}")

        if result.status != "ok":
            ctx.exit(1)


def _show_plan_human(plan: Plan) -> None:
    branch = plan.params.get("branch", "")
    create = plan.params.get("create", False)
    action = "Create & switch" if create else "Switch"
    click.echo(f"\n  {action}: {branch}")
    click.echo("  " + "\u2500" * 30)
    for step in plan.steps:
        if step.action == "stash":
            click.echo("  Stash: auto-save dirty changes")
        elif step.action == "checkout":
            flag = " (new)" if step.params.get("create") else ""
            click.echo(f"  Checkout: {step.params.get('branch', '')}{flag}")
        elif step.action == "stash_pop":
            click.echo("  Stash: restore changes")
    click.echo()

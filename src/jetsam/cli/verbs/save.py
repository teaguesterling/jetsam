"""save verb — stage + commit with smart defaults."""

import click

from jetsam.core.executor import execute_plan
from jetsam.core.output import format_json
from jetsam.core.planner import Plan, plan_save
from jetsam.core.plans import generate_plan_id
from jetsam.core.state import build_state


@click.command()
@click.argument("files", nargs=-1)
@click.option("-m", "--message", default=None, help="Commit message")
@click.option("--include", default=None, help="Glob pattern for files to include")
@click.option("--exclude", default=None, help="Glob pattern for files to exclude")
@click.option("--dry-run", is_flag=True, help="Show plan without executing")
@click.option("--execute", "auto_execute", is_flag=True, help="Execute without prompting")
@click.pass_context
def save(
    ctx: click.Context,
    files: tuple[str, ...],
    message: str | None,
    include: str | None,
    exclude: str | None,
    dry_run: bool,
    auto_execute: bool,
) -> None:
    """Stage and commit with smart defaults.

    FILES are optional explicit paths to stage. Without them, stages
    modified tracked files (or files matching --include).
    """
    state = build_state()
    plan_id = generate_plan_id()

    plan = plan_save(
        state,
        plan_id=plan_id,
        message=message,
        include=include,
        exclude=exclude,
        files=list(files) if files else None,
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
            if step_result.step == "stage":
                msg = f"Staged {step_result.details.get('files', 0)} files"
            elif step_result.step == "commit":
                sha = step_result.details.get("sha", "")
                msg = f"Committed: {step_result.details.get('message', '')} ({sha})"
            if step_result.error:
                msg = f"{step_result.step}: {step_result.error}"
            click.echo(f"  {symbol} {msg}")

        if result.status != "ok":
            ctx.exit(1)


def _show_plan_human(plan: Plan) -> None:
    click.echo(f"\n  Save: {plan.verb}")
    click.echo("  " + "\u2500" * 30)
    for step in plan.steps:
        if step.action == "stage":
            files = step.params.get("files", [])
            click.echo(f"  Stage: {', '.join(files)} ({len(files)} files)")
        elif step.action == "commit":
            click.echo(f"  Commit: \"{step.params.get('message', '')}\"")
    click.echo()

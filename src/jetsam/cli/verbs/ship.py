"""ship verb — stage + commit + push + PR in one go."""

import click

from jetsam.core.executor import execute_plan
from jetsam.core.output import format_json
from jetsam.core.planner import Plan, plan_ship
from jetsam.core.plans import generate_plan_id
from jetsam.core.state import build_state


@click.command()
@click.option("-m", "--message", default=None, help="Commit message and PR title")
@click.option("--include", default=None, help="Glob pattern for files to include")
@click.option("--exclude", default=None, help="Glob pattern for files to exclude")
@click.option("--to", "target", default=None, help="Target branch for PR (default: main/master)")
@click.option("--no-pr", is_flag=True, help="Skip PR creation")
@click.option("--merge", is_flag=True, help="Also merge the PR after creating it")
@click.option("--dry-run", is_flag=True, help="Show plan without executing")
@click.option("--execute", "auto_execute", is_flag=True, help="Execute without prompting")
@click.pass_context
def ship(
    ctx: click.Context,
    message: str | None,
    include: str | None,
    exclude: str | None,
    target: str | None,
    no_pr: bool,
    merge: bool,
    dry_run: bool,
    auto_execute: bool,
) -> None:
    """Full pipeline: stage, commit, push, open PR.

    Combines save + push + PR creation in a single command.
    """
    state = build_state()
    plan_id = generate_plan_id()

    plan = plan_ship(
        state,
        plan_id=plan_id,
        message=message,
        include=include,
        exclude=exclude,
        to=target,
        open_pr=not no_pr,
        merge=merge,
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
            if step_result.step == "stage":
                msg = f"Staged {step_result.details.get('files', 0)} files"
            elif step_result.step == "commit":
                sha = step_result.details.get("sha", "")
                msg = f"Committed: {step_result.details.get('message', '')} ({sha})"
            elif step_result.step == "push":
                remote = step_result.details.get("remote", "origin")
                branch = step_result.details.get("branch", "")
                msg = f"Pushed to {remote}/{branch}"
            elif step_result.step == "pr_create":
                url = step_result.details.get("url", "")
                num = step_result.details.get("number", "")
                msg = f"PR #{num} created: {url}"
            elif step_result.step == "pr_update":
                num = step_result.details.get("number", "")
                msg = f"PR #{num} updated via push"
            elif step_result.step == "pr_merge":
                num = step_result.details.get("number", "")
                msg = f"PR #{num} merged"
            if step_result.error:
                msg = f"{step_result.step}: {step_result.error}"
            click.echo(f"  {symbol} {msg}")

        if result.status != "ok":
            ctx.exit(1)


def _show_plan_human(plan: Plan) -> None:
    click.echo(f"\n  Ship: {plan.params.get('message', plan.verb)}")
    click.echo("  " + "\u2500" * 30)
    for step in plan.steps:
        if step.action == "stage":
            files = step.params.get("files", [])
            click.echo(f"  Stage: {', '.join(files)} ({len(files)} files)")
        elif step.action == "commit":
            click.echo(f"  Commit: \"{step.params.get('message', '')}\"")
        elif step.action == "push":
            remote = step.params.get("remote", "origin")
            branch = step.params.get("branch", "")
            click.echo(f"  Push: {remote}/{branch}")
        elif step.action == "pr_create":
            base = step.params.get("base", "main")
            click.echo(f"  PR: Create \u2192 {base}")
        elif step.action == "pr_update":
            click.echo(f"  PR: Update #{step.params.get('number', '')}")
        elif step.action == "pr_merge":
            click.echo(f"  PR: Merge \u2192 {step.params.get('base', '')}")
    click.echo()

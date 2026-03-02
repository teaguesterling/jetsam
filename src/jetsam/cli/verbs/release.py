"""release verb — tag + push tag + create platform release."""

import click

from jetsam.core.executor import execute_plan
from jetsam.core.output import format_json
from jetsam.core.planner import Plan, plan_release
from jetsam.core.plans import generate_plan_id
from jetsam.core.state import build_state


@click.command()
@click.argument("tag")
@click.option("--title", default=None, help="Release title (default: tag name)")
@click.option("--notes", default="", help="Release notes")
@click.option("--draft", is_flag=True, help="Create as draft release")
@click.option("--dry-run", is_flag=True, help="Show plan without executing")
@click.option("--execute", "auto_execute", is_flag=True, help="Execute without prompting")
@click.pass_context
def release(
    ctx: click.Context,
    tag: str,
    title: str | None,
    notes: str,
    draft: bool,
    dry_run: bool,
    auto_execute: bool,
) -> None:
    """Tag, push, and create a platform release.

    Creates an annotated tag, pushes it, and creates a GitHub/GitLab release.
    """
    state = build_state()
    plan_id = generate_plan_id()

    plan = plan_release(
        state,
        plan_id=plan_id,
        tag=tag,
        title=title,
        notes=notes,
        draft=draft,
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
            if step_result.step == "tag_create":
                msg = f"Tagged {step_result.details.get('tag', '')}"
            elif step_result.step == "push_tag":
                remote = step_result.details.get("remote", "origin")
                msg = f"Pushed tag to {remote}"
            elif step_result.step == "release_create":
                url = step_result.details.get("url", "")
                msg = f"Release created: {url}"
            if step_result.error:
                msg = f"{step_result.step}: {step_result.error}"
            click.echo(f"  {symbol} {msg}")

        if result.status != "ok":
            ctx.exit(1)


def _show_plan_human(plan: Plan) -> None:
    click.echo(f"\n  Release: {plan.params.get('tag', plan.verb)}")
    click.echo("  " + "\u2500" * 30)
    for step in plan.steps:
        if step.action == "tag_create":
            click.echo(f"  Tag: {step.params.get('tag', '')} ({step.params.get('message', '')})")
        elif step.action == "push_tag":
            remote = step.params.get("remote", "origin")
            click.echo(f"  Push: {step.params.get('tag', '')} \u2192 {remote}")
        elif step.action == "release_create":
            draft_label = " (draft)" if step.params.get("draft") else ""
            click.echo(f"  Release: {step.params.get('title', '')}{draft_label}")
    click.echo()

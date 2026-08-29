"""tag verb — list, create, delete, and push git tags."""

from dataclasses import asdict

import click

from jetsam.core.executor import execute_plan
from jetsam.core.output import format_json
from jetsam.core.planner import Plan, plan_tag
from jetsam.core.plans import generate_plan_id
from jetsam.core.state import build_state
from jetsam.git.parsers import parse_tag_list
from jetsam.git.wrapper import run_git_sync


@click.group(invoke_without_command=True)
@click.option("-n", "--count", default=20, help="Max tags to show in list")
@click.option("--sort", default="-v:refname", help="Sort order for tags")
@click.pass_context
def tag(ctx: click.Context, count: int, sort: str) -> None:
    """List, create, delete, and push tags."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(list_tags, count=count, sort=sort)


@tag.command(name="list")
@click.option("-n", "--count", default=20, help="Max tags to show")
@click.option("--sort", default="-v:refname", help="Sort order for tags (default: -v:refname)")
@click.pass_context
def list_tags(ctx: click.Context, count: int, sort: str) -> None:
    """List git tags with commit details."""
    fmt = "%(refname:short)|%(objectname:short)|%(creatordate:iso-strict)|%(subject)"
    args = ["tag", "-l", f"--sort={sort}", f"--format={fmt}"]

    result = run_git_sync(args)
    if not result.ok:
        click.echo(f"  ✗ {result.stderr.strip()}", err=True)
        ctx.exit(1)
        return

    entries = parse_tag_list(result.stdout)
    if count and len(entries) > count:
        entries = entries[:count]

    if ctx.obj and ctx.obj.get("json"):
        click.echo(format_json([asdict(e) for e in entries]))
    else:
        if not entries:
            click.echo("  No tags found.")
            return
        for e in entries:
            date_str = f" ({e.date[:10]})" if e.date else ""
            msg_str = f" - {e.message}" if e.message else ""
            sha_str = f" [{e.commit}]" if e.commit else ""
            click.echo(f"  • {e.name}{sha_str}{date_str}{msg_str}")


@tag.command(name="create")
@click.argument("name")
@click.option("-m", "--message", default=None, help="Tag annotation message")
@click.option("--annotate/--no-annotate", default=True, help="Create annotated tag (-a)")
@click.option("--push", is_flag=True, help="Push tag to remote after creating")
@click.option("--remote", default="origin", help="Remote name for push")
@click.option("--target", default=None, help="Commit/ref to tag (default: HEAD)")
@click.option("--dry-run", is_flag=True, help="Show plan without executing")
@click.option("--execute", "auto_execute", is_flag=True, help="Execute without prompting")
@click.pass_context
def create_tag(
    ctx: click.Context,
    name: str,
    message: str | None,
    annotate: bool,
    push: bool,
    remote: str,
    target: str | None,
    dry_run: bool,
    auto_execute: bool,
) -> None:
    """Create a new git tag."""
    state = build_state()
    plan_id = generate_plan_id()

    plan = plan_tag(
        state,
        plan_id=plan_id,
        action="create",
        tag=name,
        message=message,
        annotate=annotate,
        push=push,
        remote=remote,
        target=target,
    )
    _handle_plan_execution(ctx, plan, dry_run, auto_execute)


@tag.command(name="delete")
@click.argument("name")
@click.option("--remote", is_flag=True, help="Also delete tag from remote")
@click.option("--remote-name", default="origin", help="Remote name (default: origin)")
@click.option("--dry-run", is_flag=True, help="Show plan without executing")
@click.option("--execute", "auto_execute", is_flag=True, help="Execute without prompting")
@click.pass_context
def delete_tag(
    ctx: click.Context,
    name: str,
    remote: bool,
    remote_name: str,
    dry_run: bool,
    auto_execute: bool,
) -> None:
    """Delete a git tag."""
    state = build_state()
    plan_id = generate_plan_id()

    plan = plan_tag(
        state,
        plan_id=plan_id,
        action="delete",
        tag=name,
        push=remote,
        remote=remote_name,
    )
    _handle_plan_execution(ctx, plan, dry_run, auto_execute)


@tag.command(name="push")
@click.argument("name")
@click.option("--remote", default="origin", help="Remote name for push")
@click.option("--dry-run", is_flag=True, help="Show plan without executing")
@click.option("--execute", "auto_execute", is_flag=True, help="Execute without prompting")
@click.pass_context
def push_tag(
    ctx: click.Context,
    name: str,
    remote: str,
    dry_run: bool,
    auto_execute: bool,
) -> None:
    """Push a git tag to remote."""
    state = build_state()
    plan_id = generate_plan_id()

    plan = plan_tag(
        state,
        plan_id=plan_id,
        action="push",
        tag=name,
        remote=remote,
    )
    _handle_plan_execution(ctx, plan, dry_run, auto_execute)


def _handle_plan_execution(
    ctx: click.Context,
    plan: Plan,
    dry_run: bool,
    auto_execute: bool,
) -> None:
    json_mode = ctx.obj.get("json") if ctx.obj else False

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
                click.echo(f"  ⚠ {w}")

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
            symbol = "✓" if step_result.ok else "✗"
            msg = step_result.step
            if step_result.step == "tag_create":
                tag = step_result.details.get("tag", "")
                msg = f"Created tag {tag}"
            elif step_result.step == "tag_delete":
                tag = step_result.details.get("tag", "")
                msg = f"Deleted tag {tag}"
            elif step_result.step == "push_tag":
                tag = step_result.details.get("tag", "")
                remote = step_result.details.get("remote", "origin")
                msg = f"Pushed tag {tag} to {remote}"
            elif step_result.step == "push_tag_delete":
                tag = step_result.details.get("tag", "")
                remote = step_result.details.get("remote", "origin")
                msg = f"Deleted remote tag {tag} on {remote}"
            if step_result.error:
                msg = f"{step_result.step}: {step_result.error}"
            click.echo(f"  {symbol} {msg}")

        if result.status != "ok":
            ctx.exit(1)


def _show_plan_human(plan: Plan) -> None:
    click.echo(f"\n  Tag: {plan.params.get('action', '')} {plan.params.get('tag', '')}")
    click.echo("  " + "─" * 30)
    for step in plan.steps:
        if step.action == "tag_create":
            ann = " (annotated)" if step.params.get("annotate") else " (lightweight)"
            click.echo(f"  Create tag: {step.params.get('tag')}{ann}")
        elif step.action == "tag_delete":
            click.echo(f"  Delete tag: {step.params.get('tag')}")
        elif step.action == "push_tag":
            click.echo(f"  Push tag: {step.params.get('tag')} -> {step.params.get('remote', 'origin')}")
        elif step.action == "push_tag_delete":
            click.echo(f"  Delete remote tag: {step.params.get('tag')} on {step.params.get('remote', 'origin')}")
    click.echo()

"""diff verb — diff with smart defaults."""

from dataclasses import asdict

import click

from jetsam.core.output import format_human_diff_stat, format_json
from jetsam.git.parsers import parse_diff_numstat
from jetsam.git.wrapper import run_git_sync


@click.command()
@click.option("--target", default=None, help="Diff target (default: main or upstream)")
@click.option("--stat", "stat_only", is_flag=True, help="Show only stat summary")
@click.option("--staged", is_flag=True, help="Show staged changes")
@click.pass_context
def diff(
    ctx: click.Context,
    target: str | None,
    stat_only: bool,
    staged: bool,
) -> None:
    """Show diff with smart defaults."""
    json_mode = ctx.obj.get("json")

    if json_mode or stat_only:
        # Use numstat for structured output
        args = ["diff", "--numstat"]
        if staged:
            args.append("--cached")
        if target:
            args.append(target)

        result = run_git_sync(args)
        if not result.ok:
            click.echo(f"  \u2717 {result.stderr.strip()}", err=True)
            ctx.exit(1)
            return

        stat = parse_diff_numstat(result.stdout)

        if json_mode:
            click.echo(format_json(asdict(stat)))
        else:
            click.echo(format_human_diff_stat(asdict(stat)))
    else:
        # Human mode — pass through to git diff
        args = ["diff"]
        if staged:
            args.append("--cached")
        if target:
            args.append(target)

        result = run_git_sync(args)
        if result.stdout:
            click.echo(result.stdout, nl=False)
        if result.stderr:
            click.echo(result.stderr, nl=False, err=True)
        ctx.exit(result.returncode)

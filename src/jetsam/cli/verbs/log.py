"""log verb — condensed commit history."""

from dataclasses import asdict

import click

from jetsam.core.output import format_human_log, format_json
from jetsam.git.parsers import parse_log
from jetsam.git.wrapper import run_git_sync

LOG_FORMAT = "%H%x00%h%x00%an%x00%aI%x00%s"


@click.command()
@click.option("-n", "--count", default=10, help="Number of commits to show")
@click.option("--branch", default=None, help="Branch to show log for")
@click.pass_context
def log(ctx: click.Context, count: int, branch: str | None) -> None:
    """Show condensed commit history."""
    args = ["log", f"--format={LOG_FORMAT}", f"-{count}"]
    if branch:
        args.append(branch)

    result = run_git_sync(args)
    if not result.ok:
        click.echo(f"  \u2717 {result.stderr.strip()}", err=True)
        ctx.exit(1)
        return

    entries = parse_log(result.stdout)

    if ctx.obj.get("json"):
        click.echo(format_json([asdict(e) for e in entries]))
    else:
        click.echo(format_human_log([asdict(e) for e in entries]))

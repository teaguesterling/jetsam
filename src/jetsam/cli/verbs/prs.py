"""prs verb — list pull requests with check/review status."""

import click

from jetsam.core.output import format_json
from jetsam.core.state import build_state
from jetsam.platforms import get_platform


@click.command()
@click.option("--state", "pr_state", default="open",
              type=click.Choice(["open", "closed", "merged", "all"]),
              help="Filter by state (default: open)")
@click.option("--author", default=None, help="Filter by author")
@click.pass_context
def prs(
    ctx: click.Context,
    pr_state: str,
    author: str | None,
) -> None:
    """List pull requests with check and review status."""
    state = build_state()
    platform = get_platform(state.platform, cwd=state.repo_root)

    if platform is None:
        click.echo("  No platform configured (need GitHub or GitLab remote)")
        ctx.exit(1)
        return

    json_mode = ctx.obj.get("json")
    pr_list = platform.pr_list(state=pr_state, author=author)

    if json_mode:
        from dataclasses import asdict
        click.echo(format_json([asdict(p) for p in pr_list]))
    else:
        if not pr_list:
            click.echo("  No PRs found")
            return
        for p in pr_list:
            draft = " (draft)" if p.draft else ""
            status_parts: list[str] = []
            if p.checks:
                status_parts.append(f"checks: {p.checks}")
            if p.reviews:
                status_parts.append(f"reviews: {p.reviews}")
            status_str = f"  ({', '.join(status_parts)})" if status_parts else ""
            click.echo(
                f"  #{p.number} {p.title}{draft}  "
                f"[{p.state}]{status_str}"
            )
            click.echo(f"    {p.head} \u2192 {p.base}")

"""issues verb — list and search issues."""

import click

from jetsam.core.output import format_json
from jetsam.core.state import build_state
from jetsam.platforms import get_platform


@click.command()
@click.option("--state", "issue_state", default="open",
              type=click.Choice(["open", "closed", "all"]),
              help="Filter by state (default: open)")
@click.option("--label", "labels", multiple=True, help="Filter by label (repeatable)")
@click.pass_context
def issues(
    ctx: click.Context,
    issue_state: str,
    labels: tuple[str, ...],
) -> None:
    """List issues from the project's issue tracker."""
    state = build_state()
    platform = get_platform(state.platform, cwd=state.repo_root)

    if platform is None:
        click.echo("  No platform configured (need GitHub or GitLab remote)")
        ctx.exit(1)
        return

    json_mode = ctx.obj.get("json")
    label_list = list(labels) if labels else None
    issue_list = platform.issue_list(state=issue_state, labels=label_list)

    if json_mode:
        from dataclasses import asdict
        click.echo(format_json([asdict(i) for i in issue_list]))
    else:
        if not issue_list:
            click.echo("  No issues found")
            return
        for issue in issue_list:
            label_str = ""
            if issue.labels:
                label_str = f"  [{', '.join(issue.labels)}]"
            click.echo(f"  #{issue.number} {issue.title}  [{issue.state}]{label_str}")

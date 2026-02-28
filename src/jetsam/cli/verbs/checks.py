"""checks verb — CI check status for current branch or PR."""

import click

from jetsam.core.output import format_json
from jetsam.core.state import build_state
from jetsam.platforms import get_platform


@click.command()
@click.option("--pr", "pr_number", type=int, default=None,
              help="PR number (default: current branch PR)")
@click.pass_context
def checks(ctx: click.Context, pr_number: int | None) -> None:
    """Show CI check status for the current branch or a specific PR."""
    state = build_state()

    platform = get_platform(state.platform, cwd=state.repo_root)

    if platform is None:
        click.echo("  No platform configured (need GitHub or GitLab remote)")
        ctx.exit(1)
        return

    json_mode = ctx.obj.get("json")

    # Resolve PR number
    actual_pr = pr_number
    if actual_pr is None:
        pr_info = platform.pr_for_branch(state.branch)
        if pr_info is None:
            if json_mode:
                click.echo(format_json({"error": "no_pr", "branch": state.branch}))
            else:
                click.echo(f"  No PR found for branch {state.branch}")
            ctx.exit(1)
            return
        actual_pr = pr_info.number

    check_results = platform.pr_checks(actual_pr)

    if json_mode:
        from dataclasses import asdict
        click.echo(format_json([asdict(c) for c in check_results]))
    else:
        if not check_results:
            click.echo(f"  No checks found for PR #{actual_pr}")
            return

        click.echo(f"  Checks for PR #{actual_pr}:")
        for c in check_results:
            symbol = {
                "pass": "\u2713",
                "fail": "\u2717",
                "pending": "\u25cb",
                "neutral": "\u2500",
            }.get(c.status, "?")
            click.echo(f"  {symbol} {c.name}  [{c.status}]")

        passing = sum(1 for c in check_results if c.status == "pass")
        total = len(check_results)
        click.echo(f"  {passing}/{total} passing")

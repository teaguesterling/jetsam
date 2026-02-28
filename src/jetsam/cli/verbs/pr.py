"""pr verb — create, view, and list pull requests."""

import click

from jetsam.core.output import format_json
from jetsam.core.state import build_state
from jetsam.platforms import get_platform
from jetsam.platforms.base import Platform


@click.group(invoke_without_command=True)
@click.pass_context
def pr(ctx: click.Context) -> None:
    """Pull request operations.

    Without a subcommand, shows the PR for the current branch.
    """
    if ctx.invoked_subcommand is not None:
        return

    state = build_state()
    platform = _get_platform(state)
    if platform is None:
        click.echo("  No platform configured (need GitHub remote)")
        ctx.exit(1)
        return

    pr_info = platform.pr_for_branch(state.branch)
    json_mode = ctx.obj.get("json")

    if pr_info is None:
        if json_mode:
            click.echo(format_json({"pr": None, "branch": state.branch}))
        else:
            click.echo(f"  No PR found for branch {state.branch}")
        return

    if json_mode:
        from dataclasses import asdict
        click.echo(format_json(asdict(pr_info)))
    else:
        _show_pr_human(pr_info)


@pr.command("create")
@click.option("-t", "--title", default=None, help="PR title (default: branch name)")
@click.option("-b", "--body", default="", help="PR body")
@click.option("--base", default=None, help="Base branch (default: main/master)")
@click.option("--draft", is_flag=True, help="Create as draft PR")
@click.pass_context
def pr_create(
    ctx: click.Context,
    title: str | None,
    body: str,
    base: str | None,
    draft: bool,
) -> None:
    """Create a new pull request."""
    state = build_state()
    platform = _get_platform(state)
    if platform is None:
        click.echo("  No platform configured")
        ctx.exit(1)
        return

    actual_title = title or state.branch
    actual_base = base or state.default_branch
    json_mode = ctx.obj.get("json")

    try:
        pr_info = platform.pr_create(
            title=actual_title,
            body=body,
            base=actual_base,
            draft=draft,
        )
        if json_mode:
            from dataclasses import asdict
            click.echo(format_json(asdict(pr_info)))
        else:
            click.echo(f"  \u2713 PR #{pr_info.number} created: {pr_info.url}")
    except Exception as e:
        if json_mode:
            click.echo(format_json({"error": str(e)}))
        else:
            click.echo(f"  \u2717 {e}")
        ctx.exit(1)


@pr.command("list")
@click.option("--state", "pr_state", default="open",
              type=click.Choice(["open", "closed", "merged", "all"]),
              help="Filter by state")
@click.option("--author", default=None, help="Filter by author")
@click.pass_context
def pr_list(
    ctx: click.Context,
    pr_state: str,
    author: str | None,
) -> None:
    """List pull requests."""
    state = build_state()
    platform = _get_platform(state)
    if platform is None:
        click.echo("  No platform configured")
        ctx.exit(1)
        return

    json_mode = ctx.obj.get("json")
    prs = platform.pr_list(state=pr_state, author=author)

    if json_mode:
        from dataclasses import asdict
        click.echo(format_json([asdict(p) for p in prs]))
    else:
        if not prs:
            click.echo("  No PRs found")
            return
        for p in prs:
            draft = " (draft)" if p.draft else ""
            click.echo(f"  #{p.number} {p.title}{draft}  [{p.state}]")


def _get_platform(state: object) -> Platform | None:
    """Get the platform adapter."""
    platform_name = getattr(state, "platform", "unknown")
    cwd = getattr(state, "repo_root", None)
    return get_platform(platform_name, cwd=cwd)


def _show_pr_human(pr_info: object) -> None:
    """Display PR details in human format."""
    number = getattr(pr_info, "number", 0)
    title = getattr(pr_info, "title", "")
    state = getattr(pr_info, "state", "")
    url = getattr(pr_info, "url", "")
    base = getattr(pr_info, "base", "")
    head = getattr(pr_info, "head", "")
    draft = " (draft)" if getattr(pr_info, "draft", False) else ""
    checks = getattr(pr_info, "checks", "")
    reviews = getattr(pr_info, "reviews", "")

    click.echo(f"  PR #{number}: {title}{draft}")
    click.echo(f"  {head} \u2192 {base}  [{state}]")
    if url:
        click.echo(f"  {url}")
    if checks:
        click.echo(f"  Checks: {checks}")
    if reviews:
        click.echo(f"  Reviews: {reviews}")

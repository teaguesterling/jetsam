"""init verb — detect platform and set up jetsam config."""

import json
from pathlib import Path

import click

from jetsam.core.output import format_json
from jetsam.core.state import build_state


@click.command("init")
@click.option("--mcp", is_flag=True, help="Also generate .mcp.json for MCP integration")
@click.pass_context
def init(ctx: click.Context, mcp: bool) -> None:
    """Initialize jetsam in the current repository.

    Detects the platform, creates .jetsam/ directory,
    and optionally generates .mcp.json for agent integration.
    """
    state = build_state()
    json_mode = ctx.obj.get("json")
    results: dict[str, object] = {}

    # Create .jetsam directory
    jetsam_dir = Path(state.repo_root) / ".jetsam"
    jetsam_dir.mkdir(exist_ok=True)
    (jetsam_dir / "plans").mkdir(exist_ok=True)
    results["jetsam_dir"] = str(jetsam_dir)

    # Detect platform
    results["platform"] = state.platform or "none"
    results["remote"] = state.remote or "none"
    results["default_branch"] = state.default_branch
    results["branch"] = state.branch

    # Generate .mcp.json if requested
    if mcp:
        mcp_path = Path(state.repo_root) / ".mcp.json"
        mcp_config = {
            "mcpServers": {
                "jetsam": {
                    "command": "jetsam",
                    "args": ["serve"],
                    "type": "stdio",
                }
            }
        }
        mcp_path.write_text(json.dumps(mcp_config, indent=2) + "\n")
        results["mcp_json"] = str(mcp_path)

    if json_mode:
        click.echo(format_json(results))
    else:
        click.echo("\n  Initialized jetsam")
        click.echo("  " + "\u2500" * 30)
        click.echo(f"  Platform: {results['platform']}")
        click.echo(f"  Remote:   {results['remote']}")
        click.echo(f"  Branch:   {results['branch']} (default: {results['default_branch']})")
        click.echo(f"  Config:   {jetsam_dir}")
        if mcp:
            click.echo(f"  MCP:      {results['mcp_json']}")
        click.echo()

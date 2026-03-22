"""init verb — detect platform and set up jetsam config."""

import json
import os
from pathlib import Path

import click

from jetsam.core.output import format_json
from jetsam.core.state import build_state

# Shell alias definitions
ALIAS_MAP = {
    "jt": "jetsam",
    "jts": "jetsam status",
    "jtv": "jetsam save",
    "jty": "jetsam sync",
    "jth": "jetsam ship",
    "jtp": "jetsam ship --pr",
    "jtw": "jetsam switch",
    "jtl": "jetsam log",
    "jtd": "jetsam diff",
}

ALIAS_MARKER = "# jetsam aliases"

# Agent instruction file markers and content
AGENTS_MARKER_START = "<!-- jetsam:start -->"
AGENTS_MARKER_END = "<!-- jetsam:end -->"

AGENTS_FILE_MAP = {
    "claude": "CLAUDE.md",
    "gemini": "GEMINI.md",
    "agents": "AGENTS.md",
}

AGENTS_CONTENT = """\
<!-- jetsam:start -->
## jetsam

JetSam is a git workflow accelerator available as an MCP server. Workflow
operations (save, sync, ship, etc.) return execution plans — review the plan,
then call `confirm()` to execute. Query operations (status, log, diff, etc.)
return results directly. Use JetSam tools instead of running git or gh commands
through Bash.

### Git/GitHub Operations → JetSam

Do NOT run git or gh commands through Bash. Use these JetSam MCP tools instead:

| Instead of... | Use JetSam |
|---|---|
| `git status` | `mcp__jetsam__status` |
| `git add && git commit` | `mcp__jetsam__save` |
| `git push` / fetch+merge+push | `mcp__jetsam__sync` |
| `git add && commit && push && gh pr create` | `mcp__jetsam__ship` |
| `git checkout -b` to work on issue/feature | `mcp__jetsam__start` |
| `git checkout` / `git switch` (existing branch) | `mcp__jetsam__switch` |
| `git log` | `mcp__jetsam__log` |
| `git diff` | `mcp__jetsam__diff` |
| `gh pr merge` + branch cleanup | `mcp__jetsam__finish` |
| Branch pruning / cleanup | `mcp__jetsam__tidy` |
| `gh pr view` | `mcp__jetsam__pr_view` |
| `gh pr list` | `mcp__jetsam__pr_list` |
| `gh pr checks` / `gh run view` | `mcp__jetsam__checks` |
| `gh pr comment` | `mcp__jetsam__pr_comment` |
| `gh pr review` | `mcp__jetsam__pr_review` |
| `gh api .../comments` (read PR comments) | `mcp__jetsam__pr_comments` |
| `gh issue list` | `mcp__jetsam__issues` |
| `gh issue close` | `mcp__jetsam__issue_close` |
| `gh release create` | `mcp__jetsam__release` |
| Other git commands | `mcp__jetsam__git` (passthrough) |
<!-- jetsam:end -->
"""


def generate_alias_block_posix() -> str:
    """Generate alias block for bash/zsh."""
    lines = [ALIAS_MARKER]
    for short, full in ALIAS_MAP.items():
        lines.append(f"alias {short}='{full}'")
    lines.append(f"{ALIAS_MARKER} end")
    return "\n".join(lines) + "\n"


def generate_alias_block_fish() -> str:
    """Generate alias block for fish shell."""
    lines = [f"{ALIAS_MARKER}"]
    for short, full in ALIAS_MAP.items():
        parts = full.split(" ", 1)
        cmd = parts[0]
        args = parts[1] if len(parts) > 1 else ""
        if args:
            lines.append(f"function {short}; {cmd} {args} $argv; end")
        else:
            lines.append(f"function {short}; {cmd} $argv; end")
    lines.append(f"{ALIAS_MARKER} end")
    return "\n".join(lines) + "\n"


def detect_shell() -> str:
    """Detect current shell from $SHELL."""
    shell = os.environ.get("SHELL", "")
    if "fish" in shell:
        return "fish"
    if "zsh" in shell:
        return "zsh"
    return "bash"


def alias_config_path(shell: str) -> Path:
    """Return the config file path for the detected shell."""
    home = Path.home()
    if shell == "fish":
        return home / ".config" / "fish" / "conf.d" / "jetsam.fish"
    if shell == "zsh":
        return home / ".zshrc"
    return home / ".bashrc"


def has_alias_marker(content: str) -> bool:
    """Check if alias block is already present."""
    return ALIAS_MARKER in content


@click.command("init")
@click.option("--mcp", is_flag=True, help="Also generate .mcp.json for MCP integration")
@click.option("--aliases", is_flag=True, help="Install shell aliases (jt, jts, etc.)")
@click.option("--agents", "agents_target", default=None,
              help="Generate agent instructions file (claude, gemini, agents, none, or path)")
@click.pass_context
def init(ctx: click.Context, mcp: bool, aliases: bool, agents_target: str | None) -> None:
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
        jetsam_entry = {
            "command": "jetsam",
            "args": ["serve"],
            "type": "stdio",
        }

        # Merge into existing file if present
        existing: dict[str, object] = {}
        if mcp_path.exists():
            try:
                existing = json.loads(mcp_path.read_text())
            except (json.JSONDecodeError, OSError):
                existing = {}

        if "mcpServers" not in existing or not isinstance(existing["mcpServers"], dict):
            existing["mcpServers"] = {}
        existing["mcpServers"]["jetsam"] = jetsam_entry  # type: ignore[index]

        mcp_path.write_text(json.dumps(existing, indent=2) + "\n")
        results["mcp_json"] = str(mcp_path)

    # Generate agent instructions file if requested
    if agents_target and agents_target != "none":
        filename = AGENTS_FILE_MAP.get(agents_target, agents_target)
        agents_path = Path(state.repo_root) / filename
        agents_path.parent.mkdir(parents=True, exist_ok=True)

        if agents_path.exists():
            existing = agents_path.read_text()
            if AGENTS_MARKER_START in existing and AGENTS_MARKER_END in existing:
                # Replace between markers
                before = existing[:existing.index(AGENTS_MARKER_START)]
                after = existing[existing.index(AGENTS_MARKER_END) + len(AGENTS_MARKER_END):]
                agents_path.write_text(before + AGENTS_CONTENT.rstrip() + "\n" + after)
            else:
                # Append
                agents_path.write_text(existing.rstrip() + "\n\n" + AGENTS_CONTENT)
        else:
            agents_path.write_text(AGENTS_CONTENT)

        results["agents_file"] = str(agents_path)

    # Install shell aliases if requested
    if aliases:
        shell = detect_shell()
        config_path = alias_config_path(shell)

        block = generate_alias_block_fish() if shell == "fish" else generate_alias_block_posix()

        # Check for existing aliases
        existing_rc = ""
        if config_path.exists():
            existing_rc = config_path.read_text()

        if has_alias_marker(existing_rc):
            results["aliases"] = "already installed"
            results["aliases_file"] = str(config_path)
        else:
            config_path.parent.mkdir(parents=True, exist_ok=True)
            with config_path.open("a") as f:
                f.write("\n" + block)
            results["aliases"] = "installed"
            results["aliases_file"] = str(config_path)

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
        if agents_target and agents_target != "none":
            click.echo(f"  Agents: {results.get('agents_file', '')}")
        if aliases:
            status = results.get("aliases", "")
            path = results.get("aliases_file", "")
            if status == "already installed":
                click.echo(f"  Aliases:  already installed in {path}")
            else:
                click.echo(f"  Aliases:  installed in {path}")
                click.echo(f"           Run: source {path}")
        click.echo()

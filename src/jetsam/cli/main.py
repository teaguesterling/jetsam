"""jetsam CLI entrypoint."""

import click

from jetsam import __version__

# Short aliases for workflow verbs
ALIASES: dict[str, str] = {
    "s": "status",
    "v": "save",     # 'v' for saVe (s taken by status)
    "y": "sync",
    "l": "log",
    "d": "diff",
    "h": "ship",
    "w": "switch",
    "p": "pr",
    "c": "checks",
    "b": "start",    # 'b' for begin
    "f": "finish",
    "t": "tidy",
    "i": "issues",
}


class JetsamGroup(click.Group):
    """Custom group that passes unknown commands through to git."""

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command | None:
        # Check aliases first
        canonical = ALIASES.get(cmd_name, cmd_name)
        rv = super().get_command(ctx, canonical)
        if rv is not None:
            return rv
        return None

    def resolve_command(
        self, ctx: click.Context, args: list[str]
    ) -> tuple[str | None, click.Command | None, list[str]]:
        try:
            cmd_name, cmd, rest = super().resolve_command(ctx, args)
            if cmd is not None:
                return cmd_name, cmd, rest
        except click.UsageError:
            cmd_name = args[0] if args else None
            rest = args[1:] if args else []

        # Check alias before falling to passthrough
        if cmd_name and cmd_name in ALIASES:
            canonical = ALIASES[cmd_name]
            resolved = super().get_command(ctx, canonical)
            if resolved is not None:
                return canonical, resolved, rest

        from jetsam.cli.passthrough import make_passthrough_command

        return cmd_name, make_passthrough_command(cmd_name), rest

    def format_commands(
        self, ctx: click.Context, formatter: click.HelpFormatter
    ) -> None:
        """Override to show aliases in help."""
        super().format_commands(ctx, formatter)
        alias_lines = [(f"{short}", f"alias for {full}") for short, full in ALIASES.items()]
        if alias_lines:
            with formatter.section("Aliases"):
                formatter.write_dl(alias_lines)


@click.group(cls=JetsamGroup)
@click.version_option(__version__, prog_name="jetsam")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
@click.pass_context
def cli(ctx: click.Context, json_output: bool) -> None:
    """jetsam — Git workflow accelerator for humans and agents."""
    ctx.ensure_object(dict)
    ctx.obj["json"] = json_output


# Register all verb commands
from jetsam.cli.verbs.checks import checks  # noqa: E402
from jetsam.cli.verbs.completions import completions  # noqa: E402
from jetsam.cli.verbs.diff import diff  # noqa: E402
from jetsam.cli.verbs.finish import finish  # noqa: E402
from jetsam.cli.verbs.init import init  # noqa: E402
from jetsam.cli.verbs.issues import issues  # noqa: E402
from jetsam.cli.verbs.log import log  # noqa: E402
from jetsam.cli.verbs.pr import pr  # noqa: E402
from jetsam.cli.verbs.prs import prs  # noqa: E402
from jetsam.cli.verbs.save import save  # noqa: E402
from jetsam.cli.verbs.ship import ship  # noqa: E402
from jetsam.cli.verbs.start import start  # noqa: E402
from jetsam.cli.verbs.status import status  # noqa: E402
from jetsam.cli.verbs.switch import switch  # noqa: E402
from jetsam.cli.verbs.sync import sync  # noqa: E402
from jetsam.cli.verbs.tidy import tidy  # noqa: E402

cli.add_command(status)
cli.add_command(save)
cli.add_command(sync)
cli.add_command(ship)
cli.add_command(pr)
cli.add_command(checks)
cli.add_command(switch)
cli.add_command(init)
cli.add_command(log)
cli.add_command(diff)
cli.add_command(start)
cli.add_command(finish)
cli.add_command(tidy)
cli.add_command(issues)
cli.add_command(prs)
cli.add_command(completions)


@cli.command()
@click.option("--transport", type=click.Choice(["stdio", "sse"]), default="stdio",
              help="MCP transport")
def serve(transport: str) -> None:
    """Start MCP server."""
    from jetsam.mcp.server import serve_sse, serve_stdio

    if transport == "sse":
        serve_sse()
    else:
        serve_stdio()


def main() -> None:
    cli()


if __name__ == "__main__":
    main()

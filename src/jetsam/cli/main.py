"""jetsam CLI entrypoint."""

import click

from jetsam import __version__


class JetsamGroup(click.Group):
    """Custom group that passes unknown commands through to git."""

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command | None:
        rv = super().get_command(ctx, cmd_name)
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
            # Unknown command — fall through to passthrough
            cmd_name = args[0] if args else None
            rest = args[1:] if args else []

        from jetsam.cli.passthrough import make_passthrough_command

        return cmd_name, make_passthrough_command(cmd_name), rest


@click.group(cls=JetsamGroup)
@click.version_option(__version__, prog_name="jetsam")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
@click.pass_context
def cli(ctx: click.Context, json_output: bool) -> None:
    """jetsam — Git workflow accelerator for humans and agents."""
    ctx.ensure_object(dict)
    ctx.obj["json"] = json_output


# Register all verb commands
from jetsam.cli.verbs.diff import diff  # noqa: E402
from jetsam.cli.verbs.log import log  # noqa: E402
from jetsam.cli.verbs.save import save  # noqa: E402
from jetsam.cli.verbs.status import status  # noqa: E402
from jetsam.cli.verbs.sync import sync  # noqa: E402

cli.add_command(status)
cli.add_command(save)
cli.add_command(sync)
cli.add_command(log)
cli.add_command(diff)


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

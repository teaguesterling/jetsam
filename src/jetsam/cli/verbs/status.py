"""status verb — rich state snapshot."""

import click

from jetsam.core.output import format_human_status, format_json
from jetsam.core.state import build_state


@click.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Show repository state snapshot."""
    state = build_state()
    state_dict = state.to_dict()

    if ctx.obj.get("json"):
        click.echo(format_json(state_dict))
    else:
        click.echo(format_human_status(state_dict))

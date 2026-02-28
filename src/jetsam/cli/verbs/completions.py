"""completions verb — generate shell completion scripts."""

import click


@click.command()
@click.argument("shell", type=click.Choice(["bash", "zsh", "fish"]))
def completions(shell: str) -> None:
    """Generate shell completion script.

    Output the completion script for SHELL. Install with:

      eval "$(jetsam completions bash)"
      eval "$(jetsam completions zsh)"
      jetsam completions fish | source
    """
    # Click 8.x shell completion
    from click.shell_completion import get_completion_class

    from jetsam.cli.main import cli

    comp_cls = get_completion_class(shell)
    if comp_cls is None:
        click.echo(f"  Unsupported shell: {shell}", err=True)
        raise SystemExit(1)

    comp = comp_cls(cli, {}, "jetsam", "_JETSAM_COMPLETE")
    click.echo(comp.source())

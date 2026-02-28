"""Pass-through command dispatch to git/gh/glab."""

import click


def make_passthrough_command(cmd_name: str | None) -> click.Command:
    """Create a Click command that passes through to git."""

    @click.command(
        name=cmd_name,
        context_settings={"allow_extra_args": True, "allow_interspersed_args": False},
    )
    @click.pass_context
    def passthrough(ctx: click.Context) -> None:
        """Pass-through to git."""
        from jetsam.git.wrapper import run_git_sync

        args = [cmd_name or "", *ctx.args]
        result = run_git_sync(args)
        if ctx.obj.get("json"):
            import json as json_mod

            click.echo(json_mod.dumps({"ok": result.returncode == 0, "output": result.stdout}))
        else:
            if result.stdout:
                click.echo(result.stdout, nl=False)
            if result.stderr:
                click.echo(result.stderr, nl=False, err=True)
        ctx.exit(result.returncode)

    return passthrough

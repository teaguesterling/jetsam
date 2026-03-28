"""config verb — view and manage jetsam configuration."""

import click

from jetsam.config.manager import (
    global_config_path,
    load_config,
    repo_config_path,
    save_config,
    valid_config_keys,
)
from jetsam.core.output import format_json
from jetsam.core.state import build_state


@click.command("config")
@click.argument("key", required=False)
@click.argument("value", required=False)
@click.option("--global", "use_global", is_flag=True, help="Use global config")
@click.pass_context
def config(
    ctx: click.Context,
    key: str | None,
    value: str | None,
    use_global: bool,
) -> None:
    """View or set configuration values.

    \b
    jetsam config                     # show all config
    jetsam config <key>               # show one value
    jetsam config <key> <value>       # set a value
    jetsam config --global <key> <value>  # set globally
    """
    state = build_state()
    cfg = load_config(state.repo_root)
    json_mode = ctx.obj.get("json")
    valid_keys = valid_config_keys()

    # Set a value
    if key and value:
        if key not in valid_keys:
            click.echo(f"Error: unknown config key '{key}'", err=True)
            click.echo(f"Valid keys: {', '.join(sorted(valid_keys))}", err=True)
            raise SystemExit(1)

        path = str(global_config_path()) if use_global else str(repo_config_path(state.repo_root))

        save_config(path, key, value)

        if json_mode:
            click.echo(format_json({"key": key, "value": value, "path": path}))
        else:
            click.echo(f"  Set {key} = {value} in {path}")
        return

    # View a single value
    if key:
        if key not in valid_keys:
            click.echo(f"Error: unknown config key '{key}'", err=True)
            raise SystemExit(1)

        val = getattr(cfg, key)
        if json_mode:
            click.echo(format_json({key: val}))
        else:
            click.echo(val)
        return

    # View all config
    config_dict = {
        k: getattr(cfg, k)
        for k in sorted(valid_keys)
    }
    if json_mode:
        click.echo(format_json(config_dict))
    else:
        click.echo()
        for k, v in config_dict.items():
            click.echo(f"  {k}: {v}")
        source = cfg.config_path or "defaults"
        click.echo(f"\n  Source: {source}")
        click.echo()

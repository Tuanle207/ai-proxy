"""Typer root app for `aip` — mounts core command groups and provider sub-apps."""

from __future__ import annotations

import os

import typer

import ai_proxy.providers  # noqa: F401  built-ins self-register
from ai_proxy import __version__
from ai_proxy.cli import accounts_cmd, ops_cmd, providers_cmd, run_cmd
from ai_proxy.core.config import Settings
from ai_proxy.core.provider import registry

app = typer.Typer(help="AI Proxy: multi-provider web-AI automation.", no_args_is_help=True)
app.add_typer(run_cmd.app)
app.add_typer(accounts_cmd.app, name="accounts")
app.add_typer(providers_cmd.app, name="providers")
app.add_typer(ops_cmd.app)


@app.callback()
def main(
    ctx: typer.Context,
    config_file: str | None = typer.Option(
        None, "--config", help="Path to a YAML config file (or set AI_PROXY_CONFIG_FILE)."
    ),
    data_dir: str | None = typer.Option(
        None, "--data-dir", help="Override the data directory (accounts, sessions, outputs)."
    ),
) -> None:
    if config_file:
        os.environ["AI_PROXY_CONFIG_FILE"] = config_file
    ctx.obj = Settings(data_dir=data_dir) if data_dir else Settings()


@app.command()
def version() -> None:
    """Print the installed version."""
    typer.echo(__version__)


# Mount each provider's optional CLI sub-app as `aip <name-with-dashes>`.
for _name in registry.names():
    _spec = registry.get(_name)
    if _spec.cli_app is not None:
        app.add_typer(_spec.cli_app, name=_name.replace("_", "-"))


if __name__ == "__main__":
    app()

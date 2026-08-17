"""`aip providers list|show`: capability discovery."""

from __future__ import annotations

import typer

from ai_proxy.core.provider import registry
from ai_proxy.core.provider.params import json_schema
from ai_proxy.core.provider.registry import UnknownProviderError

app = typer.Typer(help="Discover registered providers.", no_args_is_help=True)


@app.command("list")
def list_providers() -> None:
    """List registered providers and their task kinds."""
    registry.discover()
    for name in registry.names():
        spec = registry.get(name)
        kinds = ", ".join(sorted(k.value for k in spec.capabilities.task_kinds))
        typer.echo(f"{name}\t{spec.display_name}\tkinds={kinds}")


@app.command("show")
def show_provider(name: str) -> None:
    """Show capabilities and params for a provider."""
    try:
        spec = registry.get(name)
    except UnknownProviderError:
        raise typer.BadParameter(f"unknown provider {name!r}") from None
    c = spec.capabilities
    typer.echo(f"name: {spec.name}")
    typer.echo(f"display_name: {spec.display_name}")
    typer.echo(f"task_kinds: {', '.join(sorted(k.value for k in c.task_kinds))}")
    typer.echo(f"max_outputs_per_request: {c.max_outputs_per_request}")
    typer.echo(f"supports_reference_inputs: {c.supports_reference_inputs}")
    typer.echo(f"supports_workspace_reuse: {c.supports_workspace_reuse}")
    typer.echo(f"requires_browser: {c.requires_browser}")
    typer.echo("params:")
    for field, info in json_schema(spec.params_model).get("properties", {}).items():
        default = info.get("default", "")
        typer.echo(f"  {field}  ({info.get('type', 'any')})  default={default!r}")

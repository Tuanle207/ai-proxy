"""`aip config`, `aip doctor`, `aip serve`: operations and diagnostics."""

from __future__ import annotations

import os

import typer

from ai_proxy.core.browser.doctor import camoufox_status
from ai_proxy.core.provider import registry
from ai_proxy.core.service.container import ServiceContainer

app = typer.Typer(help="Operations and diagnostics.")
config_app = typer.Typer(help="Inspect configuration.", no_args_is_help=True)
app.add_typer(config_app, name="config")


@config_app.command("show")
def config_show(ctx: typer.Context) -> None:
    """Print the effective configuration as JSON."""
    typer.echo(ctx.obj.model_dump_json(indent=2))


@config_app.command("path")
def config_path(ctx: typer.Context) -> None:
    """Print the resolved data directory path."""
    typer.echo(str(ctx.obj.paths.root))


@app.command()
def doctor(ctx: typer.Context) -> None:
    """Check Camoufox, data dir, and per-provider registration."""
    settings = ctx.obj
    installed, message = camoufox_status()
    typer.echo(f"Camoufox: {'OK' if installed else 'MISSING'} ({message})")
    typer.echo(f"Data dir: {settings.paths.root}")
    registry.discover()
    typer.echo("Providers:")
    for name in registry.names():
        spec = registry.get(name)
        kinds = ", ".join(sorted(k.value for k in spec.capabilities.task_kinds))
        typer.echo(f"  {name}\t{spec.display_name}\tkinds={kinds}")
    if not installed:
        raise typer.Exit(code=1)


@app.command()
def serve(
    ctx: typer.Context,
    host: str = typer.Option("127.0.0.1", "--host", help="Bind address."),
    port: int = typer.Option(8080, "--port", help="Bind port."),
    reload: bool = typer.Option(False, "--reload", help="Auto-reload on code changes."),
    show_api_key: bool = typer.Option(
        False, "--show-api-key", help="Print the active API key and exit."
    ),
) -> None:
    """Run the REST + SSE service (single worker only)."""
    settings = ctx.obj
    if int(os.environ.get("WEB_CONCURRENCY", "1")) > 1:
        typer.echo(
            "error: the service must run with a single worker "
            "(set WEB_CONCURRENCY/--workers to 1)",
            err=True,
        )
        raise typer.Exit(code=1)
    if show_api_key:
        container = ServiceContainer(settings)
        typer.echo(container.api_key)
        raise typer.Exit()
    import uvicorn

    os.environ.setdefault("AI_PROXY_DATA_DIR", settings.data_dir)
    uvicorn.run(
        "ai_proxy.core.service.app:create_app",
        host=host,
        port=port,
        reload=reload,
        factory=True,
    )

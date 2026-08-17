"""`aip run` / `aip run-batch`: provider-parametrized task submission."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer
from pydantic import ValidationError

from ai_proxy.core.client import AIProxyClient
from ai_proxy.core.models import TaskKind, TaskRequest
from ai_proxy.core.provider import registry
from ai_proxy.core.provider.registry import UnknownProviderError
from ai_proxy.core.provider.spec import ProviderSpec

app = typer.Typer(help="Run tasks against a provider.", no_args_is_help=True)


def _coerce(value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _resolve_spec(provider: str | None, default_provider: str) -> ProviderSpec:
    name = provider or default_provider
    try:
        return registry.get(name)
    except UnknownProviderError:
        raise typer.BadParameter(f"unknown provider {name!r}") from None


def _parse_params(pairs: list[str], spec: ProviderSpec) -> dict[str, Any]:
    params: dict[str, Any] = {}
    for pair in pairs:
        if "=" not in pair:
            raise typer.BadParameter(f"invalid param {pair!r}; expected key=value")
        key, _, value = pair.partition("=")
        params[key] = _coerce(value)
    try:
        spec.params_model.model_validate(params)
    except ValidationError as exc:
        raise typer.BadParameter(f"invalid params for {spec.name!r}: {exc.errors()}") from exc
    return params


@app.command("run")
def run(
    ctx: typer.Context,
    prompt: str,
    provider: str | None = typer.Option(None, "--provider", help="Provider name."),
    kind: str = typer.Option("image", "--kind", help="Task kind (image/text/video/file)."),
    count: int = typer.Option(1, "--count"),
    timeout: float | None = typer.Option(None, "--timeout"),
    params: list[str] = typer.Option([], "-p", "--param", help="key=value (repeatable)."),
) -> None:
    """Run one prompt against a provider."""
    settings = ctx.obj
    spec = _resolve_spec(provider, settings.default_provider)
    parsed = _parse_params(params, spec)
    client = AIProxyClient(settings, provider=spec.name)
    request = TaskRequest(
        provider=spec.name,
        kind=TaskKind(kind),
        prompt=prompt,
        count=count,
        timeout=timeout or settings.default_timeout_seconds,
        params=parsed,
    )
    result = client.run_sync(request)
    typer.echo(f"Completed {len(result.artifacts)} artifact(s) using {result.account_email}")
    for artifact in result.artifacts:
        if artifact.text is not None:
            typer.echo(artifact.text)
        elif artifact.rel_path is not None:
            typer.echo(str(artifact.rel_path))


@app.command("run-batch")
def run_batch(
    ctx: typer.Context,
    prompts_file: Path = typer.Option(..., "--prompts-file", help="One prompt per line."),
    provider: str | None = typer.Option(None, "--provider", help="Provider name."),
    kind: str = typer.Option("image", "--kind", help="Task kind (image/text/video/file)."),
    count: int = typer.Option(1, "--count"),
    timeout: float | None = typer.Option(None, "--timeout"),
    params: list[str] = typer.Option([], "-p", "--param", help="key=value (repeatable)."),
) -> None:
    """Run each prompt in a file against a provider."""
    settings = ctx.obj
    spec = _resolve_spec(provider, settings.default_provider)
    parsed = _parse_params(params, spec)
    prompts = [line.strip() for line in prompts_file.read_text().splitlines() if line.strip()]
    client = AIProxyClient(settings, provider=spec.name)
    for prompt in prompts:
        request = TaskRequest(
            provider=spec.name,
            kind=TaskKind(kind),
            prompt=prompt,
            count=count,
            timeout=timeout or settings.default_timeout_seconds,
            params=parsed,
        )
        result = client.run_sync(request)
        typer.echo(f"[{prompt!r}] {len(result.artifacts)} artifact(s) via {result.account_email}")

"""`aip accounts --provider <name> ...`: provider-scoped account management.

Login and health checks route through the provider's registered `AuthHandler` (via the registry)
rather than any single provider's auth module, so a second provider (perplexity) plugs in with no
core changes. Each provider owns its login probe and interactive-login flow.
"""

from __future__ import annotations

import asyncio
from typing import Any

import typer

from ai_proxy.core.accounts.manager import AccountManager
from ai_proxy.core.browser.camoufox_backend import CamoufoxBackend
from ai_proxy.core.logging_setup import get_logger
from ai_proxy.core.models import Account, AccountStatus
from ai_proxy.core.provider import registry
from ai_proxy.core.provider.auth import AuthHandler
from ai_proxy.core.provider.registry import UnknownProviderError
from ai_proxy.core.provider.session import ProviderRuntimeDeps, ProviderSession
from ai_proxy.core.service.storage import LocalStorage

app = typer.Typer(help="Manage provider accounts.", no_args_is_help=True)

_provider_opt = typer.Option(
    None, "--provider", help="Provider name (defaults to settings.default_provider)."
)


async def _noop(*args: Any, **kwargs: Any) -> None:
    return None


def _provider(ctx: typer.Context, provider: str | None) -> str:
    return provider or ctx.obj.default_provider


def _runtime(ctx: typer.Context, name: str) -> tuple[ProviderRuntimeDeps, AuthHandler]:
    """Resolve the provider and build its `AuthHandler` (settings/backend/scoped to `name`)."""
    registry.discover()
    try:
        spec = registry.get(name)
    except UnknownProviderError as exc:
        raise typer.BadParameter(f"unknown provider {name!r}") from exc
    paths = ctx.obj.paths
    deps = ProviderRuntimeDeps(
        settings=spec.settings_model(),
        paths=paths,
        backend=CamoufoxBackend(paths, name),
        storage=LocalStorage(paths.outputs_dir),
        logger=get_logger(),
    )
    return deps, spec.build_auth(deps)


def _session(account: Account, deps: ProviderRuntimeDeps) -> ProviderSession:
    return ProviderSession(
        account=account,
        page=None,
        http=None,
        paths=deps.paths,
        output_dir=deps.paths.outputs_dir,
        settings=deps.settings,
        emit=_noop,
        on_workspace_created=_noop,
    )


@app.command("add")
def add(
    ctx: typer.Context,
    email: str,
    label: str | None = typer.Option(None, "--label"),
    proxy: str | None = typer.Option(None, "--proxy"),
    login: bool = typer.Option(True, "--login/--no-login", help="Run interactive login now."),
    provider: str | None = _provider_opt,
) -> None:
    """Register a new account (runs interactive login by default)."""
    name = _provider(ctx, provider)
    manager = AccountManager(ctx.obj.paths, name)
    account = manager.add(email, label=label, proxy=proxy)
    typer.echo(f"Added {account.email} (status={account.status.value})")
    if login:
        deps, auth = _runtime(ctx, name)
        ok = asyncio.run(auth.interactive_login(_session(account, deps)))
        if ok:
            manager.set_status(account.email, AccountStatus.ACTIVE)
            typer.echo(f"{account.email} logged in and marked active.")
        else:
            typer.echo(f"{account.email} login did not complete (status left as needs_login).")


@app.command("remove")
def remove(
    ctx: typer.Context, email: str, provider: str | None = _provider_opt
) -> None:
    manager = AccountManager(ctx.obj.paths, _provider(ctx, provider))
    manager.remove(email)
    typer.echo(f"Removed {email}")


@app.command("list")
def list_accounts(ctx: typer.Context, provider: str | None = _provider_opt) -> None:
    manager = AccountManager(ctx.obj.paths, _provider(ctx, provider))
    for account in manager.list_accounts():
        typer.echo(
            f"{account.email}\t{account.status.value}\t"
            f"success={account.success_count}\tfail={account.fail_count}"
        )


@app.command("enable")
def enable(ctx: typer.Context, email: str, provider: str | None = _provider_opt) -> None:
    manager = AccountManager(ctx.obj.paths, _provider(ctx, provider))
    manager.enable(email)
    typer.echo(f"{email} enabled")


@app.command("disable")
def disable(ctx: typer.Context, email: str, provider: str | None = _provider_opt) -> None:
    manager = AccountManager(ctx.obj.paths, _provider(ctx, provider))
    manager.disable(email)
    typer.echo(f"{email} disabled")


@app.command("login")
def login(
    ctx: typer.Context,
    email: str,
    provider: str | None = _provider_opt,
) -> None:
    """Force a fresh interactive login for an existing account."""
    name = _provider(ctx, provider)
    manager = AccountManager(ctx.obj.paths, name)
    account = manager.get(email)
    deps, auth = _runtime(ctx, name)
    ok = asyncio.run(auth.interactive_login(_session(account, deps)))
    if ok:
        manager.set_status(account.email, AccountStatus.ACTIVE)
        typer.echo(f"{account.email} relogin complete")
    else:
        typer.echo(f"{account.email} relogin did not complete.", err=True)


@app.command("health")
def health(ctx: typer.Context, provider: str | None = _provider_opt) -> None:
    """Check whether each account's stored session is still logged in."""
    name = _provider(ctx, provider)
    manager = AccountManager(ctx.obj.paths, name)
    deps, auth = _runtime(ctx, name)

    async def _check_all() -> dict[str, bool]:
        results: dict[str, bool] = {}
        for account in manager.list_accounts():
            results[account.email] = await auth.is_logged_in(_session(account, deps))
        return results

    results = asyncio.run(_check_all())
    for email, ok in results.items():
        typer.echo(f"{email}\t{'ok' if ok else 'needs_login'}")
        current_status = manager.get(email).status
        if not ok:
            manager.set_status(email, AccountStatus.NEEDS_LOGIN)
        elif current_status in (AccountStatus.NEEDS_LOGIN, AccountStatus.COOLDOWN):
            manager.set_status(email, AccountStatus.ACTIVE)

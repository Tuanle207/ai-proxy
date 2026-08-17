"""ProviderSpec and Capabilities: declarative provider description."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass

import typer
from fastapi import APIRouter

from ai_proxy.core.config import ProviderSettings
from ai_proxy.core.db.engine import Database
from ai_proxy.core.db.jobs_repo import JobRecord
from ai_proxy.core.db.migrations import Migration
from ai_proxy.core.models import TaskKind
from ai_proxy.core.provider.adapter import ProviderAdapter
from ai_proxy.core.provider.auth import AuthHandler
from ai_proxy.core.provider.params import ProviderParams
from ai_proxy.core.provider.session import ProviderRuntimeDeps


@dataclass(frozen=True)
class Capabilities:
    """What a provider can do — the API/CLI discovery surface."""

    task_kinds: frozenset[TaskKind]
    max_outputs_per_request: int
    supports_reference_inputs: bool
    supports_workspace_reuse: bool
    requires_browser: bool


@dataclass(frozen=True)
class ProviderSpec:
    """Self-description a provider registers so core can resolve it by name."""

    name: str
    display_name: str
    capabilities: Capabilities
    params_model: type[ProviderParams]
    settings_model: type[ProviderSettings]
    build_adapter: Callable[[ProviderRuntimeDeps], ProviderAdapter]
    build_auth: Callable[[ProviderRuntimeDeps], AuthHandler]
    migrations: Sequence[Migration] = ()
    api_router: APIRouter | None = None
    cli_app: typer.Typer | None = None
    # Optional recovery hook: core's startup recovery calls it (with the live db) for each
    # interrupted `running` job so a provider can archive its workspace reference.
    on_orphan: Callable[[Database, JobRecord], Awaitable[None]] | None = None

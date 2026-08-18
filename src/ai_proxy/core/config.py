"""Application settings, loaded from a YAML config file and/or environment variables.

Core keeps only provider-agnostic keys. Per-provider settings live in the `providers` map,
resolved from the YAML `providers:` section and `AI_PROXY_<PROVIDER>_*` env vars
(env wins) — Flow keys never sit in core config (Phase 3.6).
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Self, cast

import yaml
from pydantic import model_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

from ai_proxy.core.paths import DataPaths

_legacy_prefix = "FLOW_"
_env_prefix = "AI_PROXY_"
DEFAULT_PROVIDER = "google_flow"


def _load_yaml_config() -> dict[str, Any]:
    """Load the YAML mapping at AI_PROXY_CONFIG_FILE, if it exists."""
    config_path = os.environ.get("AI_PROXY_CONFIG_FILE")
    if not config_path:
        return {}
    path = Path(config_path).expanduser()
    if not path.is_file():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"config file {path} must contain a YAML mapping")
    return data


def _coerce(value: str) -> Any:
    """Coerce an env-var string to bool/int/float/list/dict when it parses as JSON."""
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _merge_provider_settings() -> dict[str, dict[str, Any]]:
    """Merge the YAML `providers:` section with `AI_PROXY_<PROVIDER>_<KEY>` env vars.

    Env vars win over YAML. Provider names for env parsing come from the YAML `providers`
    keys plus `default_provider` — an `AI_PROXY_<REST>` var that matches no known provider
    prefix is a core setting and is ignored here.
    """
    merged: dict[str, dict[str, Any]] = {}
    yaml_providers = _load_yaml_config().get("providers")
    if isinstance(yaml_providers, dict):
        for provider, keys in yaml_providers.items():
            if isinstance(keys, dict):
                merged[str(provider)] = dict(keys)

    known = set(merged) | {DEFAULT_PROVIDER}
    for var, value in os.environ.items():
        if not var.startswith(_env_prefix):
            continue
        rest = var[len(_env_prefix):]
        for provider in known:
            prefix = provider.upper() + "_"
            if rest.startswith(prefix):
                key = rest[len(prefix):].lower()
                merged.setdefault(provider, {})[key] = _coerce(value)
                break
    return merged


def _yaml_config_source(settings_cls: type[BaseSettings]) -> dict[str, Any]:
    data = _load_yaml_config()
    # `providers` is resolved by _providers_source (merged with env), not the plain YAML pass.
    data.pop("providers", None)
    return data


def _providers_source(settings_cls: type[BaseSettings]) -> dict[str, Any]:
    return {"providers": _merge_provider_settings()}


class Settings(BaseSettings):
    """Runtime configuration. Precedence: env vars > YAML config file > defaults."""

    model_config = SettingsConfigDict(env_prefix=_env_prefix, extra="ignore")

    data_dir: str = "data"
    headless: bool = True
    per_account_concurrency: int = 2
    default_timeout_seconds: float = 180.0
    max_retries: int = 3
    default_output_dir: str | None = None
    default_provider: str = DEFAULT_PROVIDER
    providers: dict[str, dict[str, Any]] = {}

    # --- REST service settings (§7) ---
    api_host: str = "127.0.0.1"
    api_port: int = 5002
    api_key: str | None = None
    cors_origins: list[str] = []
    max_concurrent_browsers: int = 4
    browser_idle_ttl_seconds: float = 600.0
    db_path: str | None = None
    max_batch_prompts: int = 100
    max_prompt_length: int = 20_000
    job_max_attempts: int = 3
    cooldown_minutes: int = 5
    quota_cooldown_minutes: int = 120
    sse_heartbeat_seconds: float = 15.0
    sse_queue_maxsize: int = 256
    eta_sample_size: int = 20
    eta_default_seconds: float = 90.0
    thumbnail_max_px: int = 256
    shutdown_grace_seconds: float = 120.0
    log_level: str = "INFO"
    log_format: str = "json"

    @model_validator(mode="after")
    def _warn_legacy_flow_env(self) -> Self:
        legacy = sorted(k for k in os.environ if k.startswith(_legacy_prefix))
        if legacy:
            logging.getLogger(__name__).warning(
                "ignoring legacy %s* environment variables (renamed to AI_PROXY_*): %s",
                _legacy_prefix,
                ", ".join(legacy),
            )
        return self

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Order matters: earlier sources take precedence over later ones.
        yaml_settings = lambda: _yaml_config_source(settings_cls)  # noqa: E731
        providers_settings = lambda: _providers_source(settings_cls)  # noqa: E731
        return (
            init_settings,
            env_settings,
            cast(PydanticBaseSettingsSource, providers_settings),
            cast(PydanticBaseSettingsSource, yaml_settings),
            dotenv_settings,
            file_secret_settings,
        )

    @property
    def paths(self) -> DataPaths:
        return DataPaths(self.data_dir)

    def provider_settings(self, provider: str) -> dict[str, Any]:
        """Raw settings map for `provider` (from YAML + env). Callers apply defaults."""
        return self.providers.get(provider, {})


class ProviderSettings(BaseSettings):
    """Base for per-provider settings, resolved under `AI_PROXY_<PROVIDER>_*`.

    Providers subclass this and mount their own settings module so core never imports a
    provider's config keys. Typed subclasses arrive with the google_flow provider (Phase 5.2);
    until then callers read the raw `Settings.providers` map.
    """

    model_config = SettingsConfigDict(extra="ignore")

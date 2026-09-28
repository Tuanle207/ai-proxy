"""Application settings, loaded from a YAML config file and/or environment variables."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Self, cast

import yaml
from pydantic import model_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

from ai_web_provider.core.paths import DataPaths

_legacy_prefix = "FLOW_"
_env_prefix = "AI_PROXY_"


def _load_yaml_config() -> dict[str, Any]:
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
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _merge_provider_settings() -> dict[str, dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    yaml_providers = _load_yaml_config().get("providers")
    if isinstance(yaml_providers, dict):
        for provider, keys in yaml_providers.items():
            if isinstance(keys, dict):
                merged[str(provider)] = dict(keys)

    known = set(merged) | {"google_flow"}
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
    data.pop("providers", None)
    return data


def _providers_source(settings_cls: type[BaseSettings]) -> dict[str, Any]:
    return {"providers": _merge_provider_settings()}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix=_env_prefix, extra="ignore")

    data_dir: str = "data"
    headless: bool = True
    per_account_concurrency: int = 2
    max_retries: int = 3
    providers: dict[str, dict[str, Any]] = {}

    max_concurrent_jobs: int = 4
    browser_window_width: int | None = 1280
    browser_window_height: int | None = 720
    cooldown_minutes: int = 5
    quota_cooldown_minutes: int = 120

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
        def yaml_settings() -> dict[str, Any]:
            return _yaml_config_source(settings_cls)

        def providers_settings() -> dict[str, dict[str, dict[str, Any]]]:
            return _providers_source(settings_cls)

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
        return self.providers.get(provider, {})


class ProviderSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

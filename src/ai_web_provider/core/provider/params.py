"""Provider parameter model base + JSON-Schema export."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class ProviderParams(BaseModel):
    """Base for per-provider request params.

    ``extra="forbid"`` makes an unknown/misspelled param fail fast at the CLI or API instead of
    being silently ignored by the provider.
    """

    model_config = ConfigDict(extra="forbid")


def json_schema(params_model: type[ProviderParams]) -> dict[str, Any]:
    """Return the JSON Schema for a provider's ``params_model`` (powers `/v1/providers/{name}`)."""
    return params_model.model_json_schema()

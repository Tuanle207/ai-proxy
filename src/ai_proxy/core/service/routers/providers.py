"""Provider discovery endpoints (§2.8, Phase 7): list providers + capabilities."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ai_proxy.core.provider import registry
from ai_proxy.core.provider.params import json_schema
from ai_proxy.core.provider.registry import UnknownProviderError
from ai_proxy.core.provider.spec import ProviderSpec
from ai_proxy.core.service.deps import require_api_key
from ai_proxy.core.service.schemas import CapabilitiesResponse, ProviderDetail, ProviderInfo

router = APIRouter(prefix="/v1", tags=["providers"], dependencies=[Depends(require_api_key)])


def _capabilities(spec: ProviderSpec) -> CapabilitiesResponse:
    return CapabilitiesResponse(
        task_kinds=sorted(k.value for k in spec.capabilities.task_kinds),
        max_outputs_per_request=spec.capabilities.max_outputs_per_request,
        supports_reference_inputs=spec.capabilities.supports_reference_inputs,
        supports_workspace_reuse=spec.capabilities.supports_workspace_reuse,
        requires_browser=spec.capabilities.requires_browser,
    )


@router.get("/providers", response_model=list[ProviderInfo])
async def list_providers() -> list[ProviderInfo]:
    registry.discover()
    return [
        ProviderInfo(name=name, display_name=registry.get(name).display_name,
                     capabilities=_capabilities(registry.get(name)))
        for name in registry.names()
    ]


@router.get("/providers/{name}", response_model=ProviderDetail)
async def get_provider(name: str) -> ProviderDetail:
    try:
        spec = registry.get(name)
    except UnknownProviderError:
        raise HTTPException(404, f"unknown provider {name!r}") from None
    return ProviderDetail(
        name=spec.name,
        display_name=spec.display_name,
        capabilities=_capabilities(spec),
        params_schema=json_schema(spec.params_model),
    )

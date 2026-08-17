"""Google Flow request params: Flow-specific options that never touch core."""

from __future__ import annotations

from pydantic import field_validator

from ai_proxy.core.provider.params import ProviderParams

ALLOWED_ASPECT_RATIOS = frozenset({"16:9", "4:3", "1:1", "3:4", "9:16"})


class GoogleFlowParams(ProviderParams):
    """Per-task options for a Flow image generation (validated against `ALLOWED_ASPECT_RATIOS`)."""

    model: str | None = None
    aspect_ratio: str | None = None
    count_hint: int = 1
    overlay_logo: bool = True
    reuse_latest_project: bool = True
    delete_project_after_job: bool = False

    @field_validator("aspect_ratio")
    @classmethod
    def _validate_aspect_ratio(cls, value: str | None) -> str | None:
        if value is not None and value not in ALLOWED_ASPECT_RATIOS:
            raise ValueError(
                f"aspect_ratio must be one of {sorted(ALLOWED_ASPECT_RATIOS)}; got {value!r}"
            )
        return value

"""Google Flow project-selection parameter validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ai_web_provider.providers.google_flow.params import GoogleFlowParams


@pytest.mark.parametrize(
    "removed_param", ["reuse_default_project", "reuse_latest_project", "delete_project_after_job"]
)
def test_removed_project_params_are_rejected(removed_param: str) -> None:
    with pytest.raises(ValidationError):
        GoogleFlowParams.model_validate({removed_param: True})

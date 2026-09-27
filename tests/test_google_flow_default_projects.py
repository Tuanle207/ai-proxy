"""Google Flow default-project selection parameters."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from ai_web_provider.core.paths import DataPaths
from ai_web_provider.providers.google_flow.adapter import GoogleFlowAdapter
from ai_web_provider.providers.google_flow.params import GoogleFlowParams


def test_default_project_lookup_is_case_insensitive(tmp_path: Path) -> None:
    paths = DataPaths(tmp_path)
    project_file = paths.provider_dir("google_flow") / "default_projects.json"
    project_file.parent.mkdir(parents=True)
    project_file.write_text(json.dumps({"account@example.com": "project-123"}), encoding="utf-8")

    adapter = object.__new__(GoogleFlowAdapter)
    adapter._default_projects = adapter._load_default_projects(paths)

    assert adapter._get_default_project("Account@Example.Com") == "project-123"


def test_default_project_reuse_is_opt_in() -> None:
    assert GoogleFlowParams().reuse_default_project is False
    assert GoogleFlowParams(reuse_default_project=True).reuse_default_project is True


@pytest.mark.parametrize("removed_param", ["reuse_latest_project", "delete_project_after_job"])
def test_removed_project_params_are_rejected(removed_param: str) -> None:
    with pytest.raises(ValidationError):
        GoogleFlowParams.model_validate({removed_param: True})

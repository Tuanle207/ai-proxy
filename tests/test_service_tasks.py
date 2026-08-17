"""`_validate` unit tests for `POST /v1/tasks` (no FastAPI app/container needed)."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from fastapi import HTTPException

from ai_proxy.core.config import Settings
from ai_proxy.core.service.routers.tasks import _validate
from ai_proxy.core.service.schemas import TaskSubmitRequest
from tests.fakes import make_spec


@dataclass
class _FakeContainer:
    settings: Settings


def test_workspace_ref_rejected_for_multi_prompt_batch() -> None:
    body = TaskSubmitRequest(
        provider="fake",
        kind="text",
        prompts=["one", "two"],
        workspace_ref="thread-1",
    )
    with pytest.raises(HTTPException) as exc_info:
        _validate(body, _FakeContainer(settings=Settings()), make_spec())
    assert exc_info.value.status_code == 422


def test_workspace_ref_allowed_for_single_prompt() -> None:
    body = TaskSubmitRequest(
        provider="fake",
        kind="text",
        prompts=["one"],
        workspace_ref="thread-1",
    )
    _validate(body, _FakeContainer(settings=Settings()), make_spec())  # no raise

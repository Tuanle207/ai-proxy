"""POST /v1/tasks (§2.8, Phase 7) — provider-parametrized task submission."""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import ValidationError

from ai_proxy.core.db.engine import utc_now
from ai_proxy.core.db.jobs_repo import JobRecord
from ai_proxy.core.ids import new_id
from ai_proxy.core.provider import registry
from ai_proxy.core.provider.registry import UnknownProviderError
from ai_proxy.core.provider.spec import ProviderSpec
from ai_proxy.core.service.container import ServiceContainer
from ai_proxy.core.service.deps import require_api_key
from ai_proxy.core.service.schemas import JobRef, TaskSubmitRequest, TaskSubmitResponse

router = APIRouter(prefix="/v1", tags=["tasks"], dependencies=[Depends(require_api_key)])


def _resolve_spec(body: TaskSubmitRequest) -> ProviderSpec:
    try:
        return registry.get(body.provider)
    except UnknownProviderError:
        raise HTTPException(404, f"unknown provider {body.provider!r}") from None


def _validate(body: TaskSubmitRequest, container: ServiceContainer, spec: ProviderSpec) -> None:
    settings = container.settings
    if len(body.prompts) > settings.max_batch_prompts:
        raise HTTPException(
            422, f"too many prompts: maximum is {settings.max_batch_prompts} per batch"
        )
    for prompt in body.prompts:
        if len(prompt) > settings.max_prompt_length:
            raise HTTPException(
                422, f"prompt too long: maximum is {settings.max_prompt_length} characters"
            )
    supported = {k.value for k in spec.capabilities.task_kinds}
    if body.kind not in supported:
        raise HTTPException(
            422,
            f"kind {body.kind!r} not supported by provider {spec.name!r}; "
            f"supported: {sorted(supported)}",
        )
    if body.count > spec.capabilities.max_outputs_per_request:
        raise HTTPException(
            422,
            f"count {body.count} exceeds max_outputs_per_request "
            f"{spec.capabilities.max_outputs_per_request}",
        )
    try:
        spec.params_model.model_validate(body.params)
    except ValidationError as exc:
        raise HTTPException(
            422, f"invalid params for provider {spec.name!r}: {exc.errors()}"
        ) from exc


@router.post("/tasks", status_code=202, response_model=TaskSubmitResponse)
async def submit_task(
    request: Request,
    response: Response,
    body: TaskSubmitRequest,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
) -> TaskSubmitResponse:
    container: ServiceContainer = request.app.state.container
    spec = _resolve_spec(body)
    _validate(body, container, spec)

    if idempotency_key:
        existing = await container.jobs.get_batch_by_idempotency_key(idempotency_key)
        if existing is not None:
            response.status_code = 200
            return await _replayed_response(container, existing.id)

    batch_id = new_id("btc")
    now = utc_now()
    jobs = [
        JobRecord(
            id=new_id("job"),
            batch_id=batch_id,
            prompt=prompt,
            provider=body.provider,
            kind=body.kind,
            params=body.params,
            provider_state=None,
            count=body.count,
            timeout_seconds=body.timeout_seconds,
            priority=body.priority,
            status="queued",
            attempt=0,
            max_attempts=container.settings.job_max_attempts,
            attempted_emails=[],
            account_email=None,
            workspace_ref=None,
            error_code=None,
            error_message=None,
            queued_at=now,
            started_at=None,
            finished_at=None,
            duration_seconds=None,
            created_at=now,
            updated_at=now,
        )
        for prompt in body.prompts
    ]
    await container.jobs.create_batch_with_jobs(
        batch_id, idempotency_key=idempotency_key, metadata=body.metadata, jobs=jobs
    )
    positions = await container.engine.submit_jobs(jobs)

    total_slots = container.engine.total_slots()
    eta = container.engine.eta
    start_at = finish_at = None
    if eta.is_ready():
        first = min(positions.values())
        last = max(positions.values())
        start_at = now + timedelta(seconds=eta.start_eta(first, total_slots))
        finish_at = now + timedelta(seconds=eta.finish_eta(last, total_slots))

    return TaskSubmitResponse(
        batch_id=batch_id,
        status="queued",
        jobs=[
            JobRef(
                job_id=job.id, prompt=job.prompt, status=job.status,
                queue_position=positions[job.id],
            )
            for job in jobs
        ],
        estimated_start_at=start_at,
        estimated_finish_at=finish_at,
        warnings=[],
    )


async def _replayed_response(
    container: ServiceContainer, batch_id: str
) -> TaskSubmitResponse:
    batch = await container.jobs.get_batch(batch_id)
    jobs = await container.jobs.list_jobs_in_batch(batch_id)
    return TaskSubmitResponse(
        batch_id=batch_id,
        status=batch.status if batch else "queued",
        jobs=[
            JobRef(job_id=job.id, prompt=job.prompt, status=job.status, queue_position=None)
            for job in jobs
        ],
    )

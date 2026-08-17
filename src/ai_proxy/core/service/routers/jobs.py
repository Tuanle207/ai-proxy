"""Job & batch query/cancel endpoints (§3.2, S-06, S-10)."""

from __future__ import annotations

from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ai_proxy.core.service.container import ServiceContainer
from ai_proxy.core.service.deps import require_api_key
from ai_proxy.core.service.schemas import (
    BatchResponse,
    JobResponse,
    Page,
    RunningJobResponse,
)
from ai_proxy.core.service.serializers import (
    batch_to_response,
    job_to_response,
    running_job_to_response,
)

router = APIRouter(prefix="/v1", tags=["jobs"], dependencies=[Depends(require_api_key)])


def _container(request: Request) -> ServiceContainer:
    return cast(ServiceContainer, request.app.state.container)


@router.get("/jobs", response_model=Page[JobResponse])
async def list_jobs(
    request: Request,
    status: Annotated[list[str] | None, Query()] = None,
    batch_id: str | None = None,
    provider: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
    order: str = "queued_at:desc",
) -> Page[JobResponse]:
    container = _container(request)
    records, total = await container.jobs.list_jobs(
        statuses=status, batch_id=batch_id, provider=provider,
        page=page, page_size=page_size, order=order,
    )
    items = [job_to_response(record, [], eta=container.engine.eta) for record in records]
    return Page(
        items=items, page=page, page_size=page_size, total=total,
        has_next=page * page_size < total,
    )


@router.get("/jobs/running", response_model=list[RunningJobResponse])
async def list_running_jobs(request: Request) -> list[RunningJobResponse]:
    container = _container(request)
    records = await container.jobs.list_running()
    return [
        running_job_to_response(record, eta=container.engine.eta) for record in records
    ]


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(request: Request, job_id: str) -> JobResponse:
    container = _container(request)
    job = await container.jobs.get_job(job_id)
    if job is None:
        raise HTTPException(404, f"job {job_id} not found")
    images = await container.artifacts.list_by_job(job_id)
    return job_to_response(job, images, eta=container.engine.eta)


@router.post("/jobs/{job_id}/cancel", response_model=JobResponse)
async def cancel_job(request: Request, job_id: str) -> JobResponse:
    container = _container(request)
    if not await container.engine.cancel_job(job_id):
        job = await container.jobs.get_job(job_id)
        if job is None:
            raise HTTPException(404, f"job {job_id} not found")
    else:
        job = await container.jobs.get_job(job_id)
    assert job is not None
    images = await container.artifacts.list_by_job(job_id)
    return job_to_response(job, images, eta=container.engine.eta)


@router.get("/batches/{batch_id}", response_model=BatchResponse)
async def get_batch(request: Request, batch_id: str) -> BatchResponse:
    container = _container(request)
    batch = await container.jobs.get_batch(batch_id)
    if batch is None:
        raise HTTPException(404, f"batch {batch_id} not found")
    jobs = await container.jobs.list_jobs_in_batch(batch_id)
    total_slots = container.engine.total_slots()
    return batch_to_response(
        batch, jobs, eta=container.engine.eta, total_slots=total_slots
    )


@router.post("/batches/{batch_id}/cancel", response_model=BatchResponse)
async def cancel_batch(request: Request, batch_id: str) -> BatchResponse:
    container = _container(request)
    batch = await container.jobs.get_batch(batch_id)
    if batch is None:
        raise HTTPException(404, f"batch {batch_id} not found")
    await container.engine.cancel_batch(batch_id)
    batch = await container.jobs.get_batch(batch_id)
    jobs = await container.jobs.list_jobs_in_batch(batch_id)
    assert batch is not None
    total_slots = container.engine.total_slots()
    return batch_to_response(
        batch, jobs, eta=container.engine.eta, total_slots=total_slots
    )

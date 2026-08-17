"""Serializers mapping DB records to API response models."""

from __future__ import annotations

from datetime import datetime, timedelta

from ai_proxy.core.db.artifacts_repo import ArtifactRecord
from ai_proxy.core.db.engine import utc_now
from ai_proxy.core.db.jobs_repo import BatchRecord, JobRecord
from ai_proxy.core.service.eta import EtaEstimator
from ai_proxy.core.service.schemas import (
    ArtifactResponse,
    BatchResponse,
    JobResponse,
    RunningJobResponse,
)

_TERMINAL = {"completed", "failed", "canceled"}
_VISUAL_KINDS = {"image", "video"}


def artifact_to_response(artifact: ArtifactRecord) -> ArtifactResponse:
    visual = artifact.kind in _VISUAL_KINDS
    return ArtifactResponse(
        id=artifact.id,
        job_id=artifact.job_id,
        kind=artifact.kind,
        mime=artifact.mime,
        text=artifact.text_content,
        prompt=artifact.prompt,
        created_at=artifact.created_at,
        bytes=artifact.bytes,
        width=artifact.width,
        height=artifact.height,
        format=artifact.format,
        sha256=artifact.sha256,
        meta=artifact.meta,
        url=f"/v1/artifacts/{artifact.id}/file",
        thumbnail_url=f"/v1/artifacts/{artifact.id}/thumbnail" if visual else None,
    )


def job_to_response(
    job: JobRecord,
    artifacts: list[ArtifactRecord],
    *,
    eta: EtaEstimator | None = None,
    now: datetime | None = None,
) -> JobResponse:
    now = now or utc_now()
    elapsed: float | None = None
    eta_seconds: float | None = None
    if job.started_at is not None and job.status == "running":
        elapsed = max(0.0, (now - job.started_at).total_seconds())
        if eta is not None and eta.is_ready():
            eta_seconds = round(eta.running_remaining(elapsed), 1)
    return JobResponse(
        id=job.id,
        batch_id=job.batch_id,
        provider=job.provider,
        kind=job.kind,
        prompt=job.prompt,
        count=job.count,
        timeout_seconds=job.timeout_seconds,
        params=job.params,
        priority=job.priority,
        status=job.status,
        attempt=job.attempt,
        max_attempts=job.max_attempts,
        attempted_emails=job.attempted_emails,
        account_email=job.account_email,
        workspace_ref=job.workspace_ref,
        error_code=job.error_code,
        error_message=job.error_message,
        queued_at=job.queued_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        duration_seconds=job.duration_seconds,
        created_at=job.created_at,
        updated_at=job.updated_at,
        artifacts=[artifact_to_response(artifact) for artifact in artifacts],
        elapsed_seconds=round(elapsed, 1) if elapsed is not None else None,
        eta_seconds=eta_seconds,
    )


def running_job_to_response(
    job: JobRecord, *, eta: EtaEstimator | None = None, now: datetime | None = None
) -> RunningJobResponse:
    now = now or utc_now()
    elapsed: float | None = None
    eta_seconds: float | None = None
    if job.started_at is not None:
        elapsed = max(0.0, (now - job.started_at).total_seconds())
        if eta is not None and eta.is_ready():
            eta_seconds = round(eta.running_remaining(elapsed), 1)
    return RunningJobResponse(
        id=job.id,
        batch_id=job.batch_id,
        prompt=job.prompt,
        account_email=job.account_email,
        started_at=job.started_at,
        elapsed_seconds=round(elapsed, 1) if elapsed is not None else None,
        eta_seconds=eta_seconds,
    )


def batch_to_response(
    batch: BatchRecord,
    jobs: list[JobRecord],
    *,
    eta: EtaEstimator | None = None,
    total_slots: int = 0,
    now: datetime | None = None,
) -> BatchResponse:
    now = now or utc_now()
    counts: dict[str, int] = {}
    for job in jobs:
        counts[job.status] = counts.get(job.status, 0) + 1
    total = len(jobs)
    terminal = sum(counts.get(status, 0) for status in _TERMINAL)
    progress = round(terminal / total, 3) if total else 0.0
    remaining = total - terminal
    estimated_finish: datetime | None = None
    if remaining > 0 and eta is not None and eta.is_ready() and total_slots > 0:
        estimated_finish = now + timedelta(
            seconds=eta.finish_eta(max(remaining - 1, 0), total_slots)
        )
    return BatchResponse(
        id=batch.id,
        status=batch.status,
        job_count=batch.job_count,
        metadata=batch.metadata,
        created_at=batch.created_at,
        updated_at=batch.updated_at,
        counts=counts,
        progress=progress,
        estimated_finish_at=estimated_finish,
    )

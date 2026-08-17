"""`TaskRunner`: provider-agnostic session lifecycle + adapter invocation (Phase 6).

Core owns the account slot, browser context, timing, persistence and events. A provider adapter
only drives one destination; the runner hands it a live `ProviderSession`, persists the returned
`Artifact`s, then calls `adapter.cleanup`.
"""

from __future__ import annotations

from typing import Any

from playwright.async_api import Page

from ai_proxy.core.config import Settings
from ai_proxy.core.db.artifacts_repo import ArtifactRecord, ArtifactsRepo
from ai_proxy.core.db.engine import utc_now
from ai_proxy.core.db.jobs_repo import JobRecord, JobsRepo
from ai_proxy.core.ids import new_id
from ai_proxy.core.logging_setup import get_logger
from ai_proxy.core.models import Account, Artifact, TaskKind, TaskRequest, TaskResult
from ai_proxy.core.paths import DataPaths
from ai_proxy.core.provider.runtime import ProviderRuntime
from ai_proxy.core.provider.session import Emit, ProviderSession
from ai_proxy.core.service.storage import StorageBackend
from ai_proxy.core.worker.bus import EventBus

_log = get_logger()


class TaskRunner:
    def __init__(
        self,
        settings: Settings,
        paths: DataPaths,
        storage: StorageBackend,
        artifacts: ArtifactsRepo,
        jobs: JobsRepo,
        bus: EventBus,
    ):
        self._settings = settings
        self._paths = paths
        self._storage = storage
        self._artifacts = artifacts
        self._jobs = jobs
        self._bus = bus

    async def run(
        self,
        job: JobRecord,
        account: Account,
        page: Page | None,
        runtime: ProviderRuntime,
    ) -> TaskResult:
        session = ProviderSession(
            account=account,
            page=page,
            http=None,
            paths=self._paths,
            output_dir=self._paths.job_output_dir(job.id, job.queued_at),
            settings=runtime.settings,
            emit=self._emit(job),
            on_workspace_created=lambda ref: self._jobs.set_workspace_ref(job.id, ref),
        )
        request = TaskRequest(
            provider=job.provider,
            kind=TaskKind(job.kind),
            prompt=job.prompt,
            count=job.count,
            timeout=job.timeout_seconds,
            params=job.params,
            inputs=[],
            workspace_ref=job.workspace_ref,
        )
        adapter = runtime.adapter
        result = await adapter.execute(session, request)
        await self._persist_artifacts(job, result, account.email)
        await adapter.cleanup(session, result.workspace_ref)
        return result

    def _emit(self, job: JobRecord) -> Emit:
        async def emit(type: str, payload: dict[str, Any]) -> None:
            await self._bus.publish(
                type=type, job_id=job.id, batch_id=job.batch_id, payload=payload
            )

        return emit

    async def _persist_artifacts(
        self, job: JobRecord, result: TaskResult, email: str
    ) -> int:
        records: list[ArtifactRecord] = []
        for artifact in result.artifacts:
            record = self._artifact_to_record(job, artifact, email)
            if record is not None:
                records.append(record)
        if records:
            await self._artifacts.insert_many(records)
        return len(records)

    def _artifact_to_record(
        self, job: JobRecord, artifact: Artifact, email: str
    ) -> ArtifactRecord | None:
        rel_path = artifact.rel_path.as_posix() if artifact.rel_path is not None else None
        if artifact.kind is TaskKind.TEXT:
            text = artifact.text or ""
            return ArtifactRecord(
                id=new_id("art"),
                job_id=job.id,
                storage=self._storage.name,
                rel_path=None,
                source_url=artifact.source_url,
                kind=artifact.kind.value,
                mime=artifact.mime or "text/plain",
                text_content=text,
                meta=artifact.meta,
                bytes=len(text),
                width=None,
                height=None,
                format=None,
                sha256=artifact.sha256,
                prompt=job.prompt,
                account_email=email,
                thumbnail_rel_path=None,
                created_at=utc_now(),
            )
        if rel_path is None:
            return None
        return ArtifactRecord(
            id=new_id("art"),
            job_id=job.id,
            storage=self._storage.name,
            rel_path=rel_path,
            source_url=artifact.source_url,
            kind=artifact.kind.value,
            mime=artifact.mime or "application/octet-stream",
            text_content=None,
            meta=artifact.meta,
            bytes=artifact.bytes,
            width=artifact.width,
            height=artifact.height,
            format=None,
            sha256=artifact.sha256,
            prompt=job.prompt,
            account_email=email,
            thumbnail_rel_path=None,
            created_at=utc_now(),
        )

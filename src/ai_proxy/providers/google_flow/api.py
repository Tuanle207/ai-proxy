"""Google Flow provider API router (mounted at /v1/providers/google_flow in Phase 7)."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ai_proxy.providers.google_flow.db.orphan_projects_repo import OrphanProjectsRepo

router = APIRouter(tags=["google_flow"])


def _repo(request: Request) -> OrphanProjectsRepo:
    return OrphanProjectsRepo(request.app.state.container.db)


@router.get("/projects/orphans")
async def list_orphans(request: Request) -> JSONResponse:
    orphans = await _repo(request).list_pending()
    return JSONResponse(content={"orphans": [asdict(o) for o in orphans]})


@router.post("/projects/prune")
async def prune_orphans(request: Request) -> JSONResponse:
    repo = _repo(request)
    orphans = await repo.list_pending()
    for orphan in orphans:
        await repo.mark_cleaned(orphan.id)
    return JSONResponse(content={"pruned": len(orphans)})

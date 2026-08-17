"""Perplexity provider API router (mounted at /v1/providers/perplexity by core)."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(tags=["perplexity"])


@router.get("/threads")
async def list_threads() -> JSONResponse:
    """List known Perplexity threads.

    Thread refs are stored opaquely on `jobs.workspace_ref`; a real listing lands once the
    thread lifecycle is implemented (plan P6/P7). Until then this returns an empty list.
    """
    return JSONResponse(content={"threads": []})

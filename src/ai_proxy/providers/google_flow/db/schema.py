"""Google Flow provider migrations, applied under component="google_flow"."""

from __future__ import annotations

from ai_proxy.core.db.engine import Database
from ai_proxy.core.db.jobs_repo import JobRecord
from ai_proxy.core.db.migrations import Migration, run_migrations
from ai_proxy.providers.google_flow.db.orphan_projects_repo import OrphanProjectsRepo

# The Flow-only `gf_orphan_projects` table (renamed out of core by core v3) is now owned by this
# provider and created here under its own component namespace (Phase 5.7).
GOOGLE_FLOW_MIGRATIONS: list[Migration] = [
    [
        "CREATE TABLE IF NOT EXISTS gf_orphan_projects ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "account_email TEXT NOT NULL, "
        "project_id TEXT NOT NULL, "
        "reason TEXT NOT NULL, "
        "recorded_at TEXT NOT NULL, "
        "cleaned_at TEXT)",
        "CREATE INDEX IF NOT EXISTS ix_gf_orphan_projects_pending "
        "ON gf_orphan_projects(cleaned_at)",
    ]
]


async def run_google_flow_migrations(db: Database) -> None:
    await run_migrations(db, "google_flow", GOOGLE_FLOW_MIGRATIONS)


async def archive_orphan_project(db: Database, job: JobRecord) -> None:
    """Recovery hook: archive an interrupted job's workspace_ref before the next attempt."""
    if job.account_email is None or job.workspace_ref is None:
        return
    await OrphanProjectsRepo(db).record(
        job.account_email, job.workspace_ref, reason="interrupted_by_restart"
    )

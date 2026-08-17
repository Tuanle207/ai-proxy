"""Component-namespaced schema migrations applied on startup (§5, Phase 4).

Migrations are a list of statement batches; each component (``"core"``, ``"google_flow"``, ...)
owns its own version counter in the ``schema_version(component, version)`` table. The runner
applies only what is missing for a given component, each batch inside one transaction.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TypeAlias

from ai_proxy.core.db.engine import Database

# A migration is a list of SQL statements applied atomically under a component name (Phase 4).
Migration: TypeAlias = list[str]

# Each migration is a list of statements applied atomically. Version = 1-based index.
_CORE_V1: Migration = [
    """
    CREATE TABLE batches (
      id TEXT PRIMARY KEY,
      status TEXT NOT NULL,
      job_count INTEGER NOT NULL,
      idempotency_key TEXT UNIQUE,
      metadata TEXT,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE jobs (
      id TEXT PRIMARY KEY,
      batch_id TEXT NOT NULL REFERENCES batches(id) ON DELETE CASCADE,
      prompt TEXT NOT NULL,
      model TEXT,
      aspect_ratio TEXT,
      count INTEGER NOT NULL DEFAULT 1,
      timeout_seconds REAL NOT NULL,
      overlay_logo INTEGER NOT NULL DEFAULT 1,
      priority INTEGER NOT NULL DEFAULT 0,
      status TEXT NOT NULL,
      attempt INTEGER NOT NULL DEFAULT 0,
      max_attempts INTEGER NOT NULL DEFAULT 3,
      attempted_emails TEXT NOT NULL DEFAULT '[]',
      account_email TEXT,
      project_id TEXT,
      error_code TEXT,
      error_message TEXT,
      queued_at TEXT NOT NULL,
      started_at TEXT,
      finished_at TEXT,
      duration_seconds REAL,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX ix_jobs_status_priority ON jobs(status, priority DESC, queued_at)",
    "CREATE INDEX ix_jobs_batch ON jobs(batch_id)",
    """
    CREATE TABLE images (
      id TEXT PRIMARY KEY,
      job_id TEXT REFERENCES jobs(id) ON DELETE SET NULL,
      storage TEXT NOT NULL DEFAULT 'local',
      rel_path TEXT NOT NULL UNIQUE,
      source_url TEXT,
      bytes INTEGER NOT NULL,
      width INTEGER,
      height INTEGER,
      format TEXT,
      sha256 TEXT,
      prompt TEXT,
      account_email TEXT,
      thumbnail_rel_path TEXT,
      created_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX ix_images_created ON images(created_at DESC, id DESC)",
    "CREATE INDEX ix_images_job ON images(job_id)",
    """
    CREATE TABLE job_events (
      seq INTEGER PRIMARY KEY AUTOINCREMENT,
      job_id TEXT,
      batch_id TEXT,
      type TEXT NOT NULL,
      status TEXT,
      payload TEXT NOT NULL,
      created_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX ix_events_job ON job_events(job_id, seq)",
    "CREATE INDEX ix_events_batch ON job_events(batch_id, seq)",
]

# Durably records a project that a crash-recovered job can no longer track via `jobs.project_id`
# (that column gets overwritten by the next attempt's new project — see recovery.py).
_CORE_V2: Migration = [
    """
    CREATE TABLE orphan_projects (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      account_email TEXT NOT NULL,
      project_id TEXT NOT NULL,
      reason TEXT NOT NULL,
      recorded_at TEXT NOT NULL,
      cleaned_at TEXT
    )
    """,
    "CREATE INDEX ix_orphan_projects_pending ON orphan_projects(cleaned_at)",
]

# Core v3 — the generalization: provider/kind/params on jobs, `images` → `artifacts`, and the
# Flow-only `orphan_projects` table moved out of core's namespace (owned by the provider, Phase 5).
_CORE_V3: Migration = [
    "ALTER TABLE jobs ADD COLUMN provider TEXT",
    "ALTER TABLE jobs ADD COLUMN kind TEXT",
    "ALTER TABLE jobs ADD COLUMN params TEXT",
    "ALTER TABLE jobs ADD COLUMN provider_state TEXT",
    "ALTER TABLE jobs RENAME COLUMN project_id TO workspace_ref",
    """
    UPDATE jobs SET
      provider = 'google_flow',
      kind = 'image',
      params = json_object(
        'model', model,
        'aspect_ratio', aspect_ratio,
        'overlay_logo', json(CASE overlay_logo WHEN 1 THEN 'true' ELSE 'false' END),
        'reuse_latest_project', json('false')
      )
    """,
    "ALTER TABLE jobs DROP COLUMN model",
    "ALTER TABLE jobs DROP COLUMN aspect_ratio",
    "ALTER TABLE jobs DROP COLUMN overlay_logo",
    "ALTER TABLE batches ADD COLUMN provider TEXT",
    "UPDATE batches SET provider = 'google_flow'",
    """
    CREATE TABLE artifacts (
      id TEXT PRIMARY KEY,
      job_id TEXT REFERENCES jobs(id) ON DELETE SET NULL,
      storage TEXT NOT NULL DEFAULT 'local',
      rel_path TEXT,
      source_url TEXT,
      kind TEXT,
      mime TEXT,
      text_content TEXT,
      meta TEXT,
      bytes INTEGER,
      width INTEGER,
      height INTEGER,
      format TEXT,
      sha256 TEXT,
      prompt TEXT,
      account_email TEXT,
      thumbnail_rel_path TEXT,
      created_at TEXT NOT NULL
    )
    """,
    """
    INSERT INTO artifacts (
      id, job_id, storage, rel_path, source_url, kind, mime, bytes, width, height,
      format, sha256, prompt, account_email, thumbnail_rel_path, created_at
    )
    SELECT
      id, job_id, storage, rel_path, source_url, 'image', 'image/jpeg', bytes, width, height,
      format, sha256, prompt, account_email, thumbnail_rel_path, created_at
    FROM images
    """,
    "DROP TABLE images",
    "CREATE INDEX ix_artifacts_created ON artifacts(created_at DESC, id DESC)",
    "CREATE INDEX ix_artifacts_job ON artifacts(job_id)",
    "ALTER TABLE orphan_projects RENAME TO gf_orphan_projects",
    "CREATE INDEX ix_jobs_provider_status_priority "
    "ON jobs(provider, status, priority DESC, queued_at)",
]

CORE_MIGRATIONS: list[Migration] = [_CORE_V1, _CORE_V2, _CORE_V3]


async def _upgrade_legacy_schema_version(db: Database) -> None:
    """One-shot upgrade of the pre-Phase-4 single-column `schema_version` table.

    The old table held only a `version` column (a single global counter). Detect it by absence of
    the `component` column, then carry its max version forward under `component='core'` so an
    existing dev DB continues where it left off.
    """
    info = await db.fetch_all("PRAGMA table_info(schema_version)")
    if any(row["name"] == "component" for row in info):
        return
    old = int(await db.fetch_val("SELECT COALESCE(MAX(version), 0) FROM schema_version") or 0)
    await db.execute("DROP TABLE schema_version")
    await db.execute(
        "CREATE TABLE schema_version (component TEXT PRIMARY KEY, version INTEGER NOT NULL)"
    )
    await db.execute(
        "INSERT INTO schema_version (component, version) VALUES ('core', ?)", (old,)
    )


async def run_migrations(
    db: Database, component: str, migrations: Sequence[Migration]
) -> None:
    await db.execute(
        "CREATE TABLE IF NOT EXISTS schema_version "
        "(component TEXT PRIMARY KEY, version INTEGER NOT NULL)"
    )
    await _upgrade_legacy_schema_version(db)
    current = int(
        await db.fetch_val(
            "SELECT COALESCE(version, 0) FROM schema_version WHERE component = ?",
            (component,),
        )
        or 0
    )
    for version, statements in enumerate(migrations, start=1):
        if version <= current:
            continue
        async with db.transaction():
            for statement in statements:
                await db.execute(statement)
            await db.execute(
                "INSERT OR REPLACE INTO schema_version (component, version) VALUES (?, ?)",
                (component, version),
            )


async def run_core_migrations(db: Database) -> None:
    await run_migrations(db, "core", CORE_MIGRATIONS)

"""Phase 4 tests: component-namespaced migrations and the core v3 upgrade (Task 4.7).

Three required scenarios: a fresh DB reaches core v3, a v2 fixture upgrades in place with rows
preserved and `params` reconstructed, and a provider component migrates independently of core.
A fourth covers the legacy single-column `schema_version` table upgrade (Task 4.1).
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

from ai_proxy.core.db.engine import Database
from ai_proxy.core.db.migrations import (
    CORE_MIGRATIONS,
    run_core_migrations,
    run_migrations,
)


async def _table_names(db: Database) -> set[str]:
    rows = await db.fetch_all("SELECT name FROM sqlite_master WHERE type = 'table'")
    return {row["name"] for row in rows}


def test_fresh_db_reaches_core_v3(tmp_path: Path) -> None:
    async def main() -> None:
        db = Database(tmp_path / "fresh.db")
        await db.connect()
        try:
            await run_core_migrations(db)

            version = await db.fetch_val(
                "SELECT version FROM schema_version WHERE component = 'core'"
            )
            assert version == 3

            job_cols = {r["name"] for r in await db.fetch_all("PRAGMA table_info(jobs)")}
            assert {"provider", "kind", "params", "provider_state", "workspace_ref"} <= job_cols
            assert not {"model", "aspect_ratio", "overlay_logo"} & job_cols

            tables = await _table_names(db)
            assert "artifacts" in tables
            assert "images" not in tables
        finally:
            await db.close()

    asyncio.run(main())


def test_v2_fixture_upgrades_in_place(tmp_path: Path) -> None:
    async def main() -> None:
        db = Database(tmp_path / "v2.db")
        await db.connect()
        try:
            await run_migrations(db, "core", CORE_MIGRATIONS[:2])

            now = datetime.now(UTC).isoformat()
            await db.execute(
                "INSERT INTO batches (id, status, job_count, created_at, updated_at) "
                "VALUES ('b1', 'queued', 1, ?, ?)",
                (now, now),
            )
            await db.execute(
                "INSERT INTO jobs (id, batch_id, prompt, model, aspect_ratio, count, "
                "timeout_seconds, overlay_logo, status, project_id, queued_at, created_at, "
                "updated_at) VALUES ('j1', 'b1', 'hello', 'm', '16:9', 1, 120.0, 1, "
                "'queued', 'p1', ?, ?, ?)",
                (now, now, now),
            )
            await db.execute(
                "INSERT INTO images (id, job_id, rel_path, bytes, created_at) "
                "VALUES ('img1', 'j1', 'out/x.png', 100, ?)",
                (now,),
            )
            await db.execute(
                "INSERT INTO orphan_projects (account_email, project_id, reason, recorded_at) "
                "VALUES ('a@b.com', 'p1', 'test', ?)",
                (now,),
            )

            await run_core_migrations(db)

            assert await db.fetch_val("SELECT COUNT(*) FROM jobs") == 1
            assert await db.fetch_val("SELECT COUNT(*) FROM batches") == 1
            assert await db.fetch_val("SELECT COUNT(*) FROM artifacts") == 1
            assert await db.fetch_val("SELECT COUNT(*) FROM gf_orphan_projects") == 1

            row = await db.fetch_one(
                "SELECT provider, kind, params, workspace_ref FROM jobs WHERE id = 'j1'"
            )
            assert row is not None
            assert row["provider"] == "google_flow"
            assert row["kind"] == "image"
            assert row["workspace_ref"] == "p1"
            assert json.loads(row["params"]) == {
                "model": "m",
                "aspect_ratio": "16:9",
                "overlay_logo": True,
                "reuse_latest_project": False,
            }

            tables = await _table_names(db)
            assert "gf_orphan_projects" in tables
            assert "orphan_projects" not in tables
            assert "artifacts" in tables
            assert "images" not in tables
        finally:
            await db.close()

    asyncio.run(main())


def test_provider_component_migrates_independently(tmp_path: Path) -> None:
    async def main() -> None:
        db = Database(tmp_path / "provider.db")
        await db.connect()
        try:
            migration = [["CREATE TABLE t1 (x TEXT)"]]
            await run_migrations(db, "test_provider", migration)

            version = await db.fetch_val(
                "SELECT version FROM schema_version WHERE component = 'test_provider'"
            )
            assert version == 1
            core_version = await db.fetch_val(
                "SELECT version FROM schema_version WHERE component = 'core'"
            )
            assert core_version is None

            # re-running the same component is a no-op
            await run_migrations(db, "test_provider", migration)
            version = await db.fetch_val(
                "SELECT version FROM schema_version WHERE component = 'test_provider'"
            )
            assert version == 1
        finally:
            await db.close()

    asyncio.run(main())


def test_legacy_single_column_schema_version_upgraded(tmp_path: Path) -> None:
    async def main() -> None:
        db = Database(tmp_path / "legacy.db")
        await db.connect()
        try:
            # Simulate the pre-Phase-4 DB: old single-column table already at version 1, with
            # the v1 tables present (so only v2 + v3 remain to apply after the carry-forward).
            await db.execute("CREATE TABLE schema_version (version INTEGER NOT NULL)")
            for statement in CORE_MIGRATIONS[0]:
                await db.execute(statement)
            await db.execute("INSERT INTO schema_version (version) VALUES (1)")

            await run_core_migrations(db)

            cols = {r["name"] for r in await db.fetch_all("PRAGMA table_info(schema_version)")}
            assert cols == {"component", "version"}
            version = await db.fetch_val(
                "SELECT version FROM schema_version WHERE component = 'core'"
            )
            assert version == 3
            job_cols = {r["name"] for r in await db.fetch_all("PRAGMA table_info(jobs)")}
            assert {"provider", "kind", "params", "provider_state", "workspace_ref"} <= job_cols
        finally:
            await db.close()

    asyncio.run(main())

"""In-memory leases for configured Google Flow projects."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass


@dataclass
class ProjectLease:
    _pool: GoogleFlowProjectPool
    email: str
    project_id: str
    _released: bool = False

    async def release(self) -> None:
        if not self._released:
            self._released = True
            await self._pool.release(self)


class GoogleFlowProjectPool:
    """Lease one configured project per active job for each account."""

    def __init__(self, projects_by_account: dict[str, list[str]]):
        self._projects = {
            email.strip().lower(): tuple(projects)
            for email, projects in projects_by_account.items()
        }
        self._leased: dict[str, set[str]] = {}
        self._next: dict[str, int] = {}
        self._changed = asyncio.Condition()

    async def acquire(self, email: str) -> ProjectLease:
        email = email.strip().lower()
        async with self._changed:
            projects = self._projects.get(email)
            if not projects:
                raise RuntimeError(f"no Google Flow projects configured for {email!r}")
            while True:
                leased = self._leased.setdefault(email, set())
                start = self._next.get(email, 0)
                for offset in range(len(projects)):
                    index = (start + offset) % len(projects)
                    project_id = projects[index]
                    if project_id not in leased:
                        leased.add(project_id)
                        self._next[email] = (index + 1) % len(projects)
                        return ProjectLease(self, email, project_id)
                await self._changed.wait()

    async def release(self, lease: ProjectLease) -> None:
        async with self._changed:
            self._leased.get(lease.email, set()).discard(lease.project_id)
            self._changed.notify_all()

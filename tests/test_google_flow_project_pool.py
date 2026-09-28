import asyncio

from ai_web_provider.providers.google_flow.project_pool import GoogleFlowProjectPool


def test_projects_are_leased_exclusively_and_waiters_resume() -> None:
    async def run() -> None:
        pool = GoogleFlowProjectPool({"account@example.com": ["project-a", "project-b"]})
        first = await pool.acquire("account@example.com")
        second = await pool.acquire("account@example.com")
        assert {first.project_id, second.project_id} == {"project-a", "project-b"}

        waiting = asyncio.create_task(pool.acquire("account@example.com"))
        await asyncio.sleep(0)
        assert not waiting.done()

        await first.release()
        third = await waiting
        assert third.project_id == first.project_id

        await second.release()
        await third.release()

    asyncio.run(run())

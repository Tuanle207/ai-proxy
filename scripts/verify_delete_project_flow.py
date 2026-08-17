"""One-off live check for the create-project + delete-project-after-job flow.

Records the project list before and after a real generate+delete run so we can confirm the
*correct* project was removed and nothing else was collaterally deleted (the exact bug that
made `delete_project_after_job` default to False, see config.py).

Usage: .venv\\Scripts\\python scripts\\verify_delete_project_flow.py <account_email>
"""

from __future__ import annotations

import asyncio
import sys

from google_flow_wrapper.accounts.manager import AccountManager
from google_flow_wrapper.browser.camoufox_backend import CamoufoxBackend
from google_flow_wrapper.config import Settings
from google_flow_wrapper.flowpage import navigate
from google_flow_wrapper.flowpage import selectors as sel
from google_flow_wrapper.models import GenerationRequest
from google_flow_wrapper.worker.runner import GenerationRunner


async def _list_project_hrefs(page) -> list[str]:
    links = page.locator(sel.PROJECT_LINK)
    await links.first.wait_for(state="visible", timeout=10000)
    return [await links.nth(i).get_attribute("href") for i in range(await links.count())]


async def main(email: str) -> int:
    settings = Settings()
    manager = AccountManager(settings.paths)
    account = manager.get(email)
    backend = CamoufoxBackend(settings.paths)

    async with backend.browser_context(account, headless=False) as context:
        page = await context.new_page()
        await navigate.open_flow(page)
        before = await _list_project_hrefs(page)
        await page.close()
    print(f"BEFORE: {len(before)} projects")
    for href in before[:10]:
        print(f"  {href}")

    runner = GenerationRunner(settings, backend)
    created_id: str | None = None
    deleted_called = False

    async def on_created(project_id: str) -> None:
        nonlocal created_id
        created_id = project_id
        print(f"created project_id={project_id}")

    async def on_deleted() -> None:
        nonlocal deleted_called
        deleted_called = True
        print("on_project_deleted callback fired")

    settings.delete_project_after_job = True
    request = GenerationRequest(
        prompt="a small red cube on a plain white background, verify-delete-flow", count=1
    )
    result = await runner.run(
        account,
        request,
        new_project=True,
        headless=False,
        on_project_created=on_created,
        on_project_deleted=on_deleted,
    )
    print(f"generation result: {len(result.images)} image(s), project_id={result.project_id}")
    print(f"delete callback fired: {deleted_called}")

    async with backend.browser_context(account, headless=False) as context:
        page = await context.new_page()
        await navigate.open_flow(page)
        after = await _list_project_hrefs(page)
        created_still_present = created_id is not None and any(
            f"/project/{created_id}" in href for href in after
        )
        await page.close()
    print(f"AFTER: {len(after)} projects")
    for href in after[:10]:
        print(f"  {href}")

    missing_from_before = [href for href in before if href not in after]
    extra_in_after_besides_created = [
        href
        for href in after
        if href not in before and (created_id is None or f"/project/{created_id}" not in href)
    ]
    print(f"\ncreated project still in list: {created_still_present} (expect False)")
    print(f"pre-existing projects missing after run: {missing_from_before} (expect [])")
    print(
        "unexpected new entries besides the created+deleted one: "
        f"{extra_in_after_besides_created} (expect [])"
    )
    ok = (
        not created_still_present
        and not missing_from_before
        and not extra_in_after_besides_created
        and deleted_called
    )
    print("\nRESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: verify_delete_project_flow.py <account_email>")
        raise SystemExit(2)
    raise SystemExit(asyncio.run(main(sys.argv[1])))

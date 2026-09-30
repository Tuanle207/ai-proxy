"""Generate one Google Flow image using persisted account cookies."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from ai_web_provider import (
    BrowserSettings,
    ProviderRuntimeContainer,
    Settings,
    TaskKind,
    TaskRequest,
)
from ai_web_provider.core.provider.session import ProviderSession


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--account", required=True, help="Provisioned Google Flow account email")
    parser.add_argument("--ungoogled-chromium-executable", type=Path, required=True)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--model", default="Nano Banana 2")
    parser.add_argument("--aspect-ratio", default="16:9")
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--viewport-width", type=int, default=1280)
    parser.add_argument("--viewport-height", type=int, default=720)
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> None:
    default_projects_path = args.data_dir / "providers" / "google_flow" / "default_projects.json"
    projects_by_account: dict[str, list[str]] = {}
    if default_projects_path.exists():
        raw = json.loads(default_projects_path.read_text(encoding="utf-8"))
        projects_by_account = {email: [project_id] for email, project_id in raw.items()}
    settings = Settings(
        data_dir=str(args.data_dir),
        providers={"google_flow": {"projects_by_account": projects_by_account}},
        browser=BrowserSettings(
            ungoogled_chromium_executable=args.ungoogled_chromium_executable,
            viewport_width=args.viewport_width,
            viewport_height=args.viewport_height,
        ),
    )
    container = ProviderRuntimeContainer(settings)
    await container.startup()
    try:
        runtime = container.provider("google_flow")
        account = runtime.accounts.get(args.account)
        probe_session = ProviderSession(
            account, None, container.paths, container.paths.outputs_dir, runtime.settings
        )
        if not await runtime.auth.probe_session(probe_session):
            raise RuntimeError(
                "the persisted account cookies are not authenticated; run login_google_flow.py again"
            )
        request = TaskRequest(
            provider="google_flow",
            kind=TaskKind.IMAGE,
            prompt=args.prompt,
            timeout=args.timeout,
            params={"model": args.model, "aspect_ratio": args.aspect_ratio},
        )
        async with runtime.backend.browser_context(account) as context:
            page = await context.new_page()
            await page.set_viewport_size(
                {
                    "width": settings.browser.viewport_width,
                    "height": settings.browser.viewport_height,
                }
            )
            try:
                session = ProviderSession(
                    account, page, container.paths, container.paths.outputs_dir, runtime.settings
                )
                result = await runtime.adapter.execute(session, request)
            finally:
                await page.close()
        if not result.artifacts:
            raise RuntimeError("Google Flow completed without returning an image artifact")
        for artifact in result.artifacts:
            path = container.paths.outputs_dir / artifact.rel_path if artifact.rel_path else None
            print(path or artifact.source_url or artifact.model_dump_json())
    finally:
        await container.shutdown()


if __name__ == "__main__":
    asyncio.run(_run(_arguments()))

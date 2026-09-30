"""Open headed ungoogled-chromium to authenticate one Google Flow account."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from ai_web_provider import BrowserSettings, ProviderRuntimeContainer, Settings
from ai_web_provider.core.models import AccountStatus
from ai_web_provider.core.provider.session import ProviderSession


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--account", required=True, help="Registered Google Flow account email")
    parser.add_argument("--ungoogled-chromium-executable", type=Path, required=True)
    parser.add_argument("--viewport-width", type=int, default=1280)
    parser.add_argument("--viewport-height", type=int, default=720)
    parser.add_argument("--login-timeout", type=float, default=300.0)
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> None:
    settings = Settings(
        data_dir=str(args.data_dir),
        browser=BrowserSettings(
            ungoogled_chromium_executable=args.ungoogled_chromium_executable,
            viewport_width=args.viewport_width,
            viewport_height=args.viewport_height,
            login_timeout_seconds=args.login_timeout,
        ),
    )
    container = ProviderRuntimeContainer(settings)
    await container.startup()
    try:
        runtime = container.provider("google_flow")
        account = runtime.accounts.get(args.account)
        session = ProviderSession(
            account, None, container.paths, container.paths.outputs_dir, runtime.settings
        )
        if not await runtime.auth.interactive_login(session):
            raise RuntimeError(f"login timed out or failed for {account.email}")
        runtime.accounts.set_status(account.email, AccountStatus.ACTIVE)
        print(f"Google Flow session provisioned for {account.email}")
    finally:
        await container.shutdown()


if __name__ == "__main__":
    asyncio.run(_run(_arguments()))

"""Perplexity reconnaissance tool: log in a live session and capture selectors.

Two jobs, both needed before the page-driving code (`navigate.py`/`prompt.py`/`wait.py`/
`extract.py`) can be written with confidence (plan P3.1):

1. **Login** — registers the account (if needed), opens a headed Camoufox browser at Perplexity,
   waits for you to log in manually, then persists the session to
   ``data/providers/perplexity/sessions/<email>/storage_state.json`` (done automatically when the
   context exits).

2. **Inspect** (`--inspect`) — after login, dumps a DOM report of candidate elements (textareas,
   inputs, textboxes, buttons, auth links) and then enters an interactive click-capture loop:
   click any element to print its attributes and a few suggested stable selectors.

Usage:
    .venv\\Scripts\\python scripts\\recon_perplexity.py --email you@example.com
    .venv\\Scripts\\python scripts\\recon_perplexity.py --email you@example.com --inspect
"""

from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from ai_proxy.core.accounts.manager import AccountManager
from ai_proxy.core.browser.camoufox_backend import CamoufoxBackend
from ai_proxy.core.config import Settings
from ai_proxy.core.errors import AccountNotFoundError
from ai_proxy.core.models import Account
from ai_proxy.providers.perplexity.page.selectors import PERPLEXITY_URL

_DUMP_REPORT_JS = """() => {
  const pick = (el) => ({
    tag: el.tagName,
    id: el.id || null,
    role: el.getAttribute('role') || null,
    aria: el.getAttribute('aria-label') || null,
    placeholder: el.getAttribute('placeholder') || null,
    text: (el.innerText || '').trim().slice(0, 80) || null,
    type: el.getAttribute('type') || null,
  });
  const all = (sel) => Array.from(document.querySelectorAll(sel)).map(pick);
  return {
    url: location.href,
    textareas: all('textarea'),
    inputs: all('input'),
    textboxes: all('[role="textbox"]'),
    buttons: all('button').filter((b) => b.aria || b.text),
    links: Array.from(document.querySelectorAll('a'))
      .map((a) => ({ href: a.getAttribute('href'), text: (a.innerText || '').trim().slice(0, 60) }))
      .filter((a) => a.href && (
        /search|thread|login|sign/i.test(a.href) ||
        /log in|sign in|sign up/i.test(a.text)
      )),
  };
}"""

_CAPTURE_INSTALL_JS = """() => {
  window.__captured = null;
  if (window.__clickHandler) document.removeEventListener('click', window.__clickHandler, true);
  window.__clickHandler = (e) => {
    const el = e.target;
    const anchor = el.closest('a');
    const button = el.closest('button');
    window.__captured = {
      tag: el.tagName,
      id: el.id || null,
      role: el.getAttribute('role') || null,
      aria: el.getAttribute('aria-label') || null,
      placeholder: el.getAttribute('placeholder') || null,
      cls: typeof el.className === 'string' ? el.className.slice(0, 160) : null,
      text: (el.innerText || '').trim().slice(0, 120) || null,
      href: el.getAttribute('href') || null,
      type: el.getAttribute('type') || null,
      html: el.outerHTML ? el.outerHTML.slice(0, 300) : null,
      closestAnchor: anchor ? {
        id: anchor.id || null,
        href: anchor.getAttribute('href') || null,
        target: anchor.getAttribute('target') || null,
        aria: anchor.getAttribute('aria-label') || null,
        cls: typeof anchor.className === 'string' ? anchor.className.slice(0, 160) : null,
        html: anchor.outerHTML ? anchor.outerHTML.slice(0, 300) : null,
      } : null,
      closestButton: button ? {
        id: button.id || null,
        aria: button.getAttribute('aria-label') || null,
        cls: typeof button.className === 'string' ? button.className.slice(0, 160) : null,
        html: button.outerHTML ? button.outerHTML.slice(0, 300) : null,
      } : null,
    };
    e.preventDefault();
    e.stopPropagation();
  };
  document.addEventListener('click', window.__clickHandler, true);
}"""


def _suggest(info: dict[str, Any]) -> list[str]:
    suggestions: list[str] = []
    if info.get("id"):
        suggestions.append(f"#{info['id']}")
    if info.get("placeholder"):
        suggestions.append(f"{info['tag'].lower()}[placeholder*='{info['placeholder'][:40]}']")
    if info.get("aria"):
        suggestions.append(f"[aria-label*='{info['aria'][:40]}']")
    if info.get("role"):
        suggestions.append(f"[role='{info['role']}']")
    if info.get("type"):
        suggestions.append(f"{info['tag'].lower()}[type='{info['type']}']")
    return suggestions or ["(no stable attribute — try a text/nth-based selector)"]


async def _login(account: Account, backend: CamoufoxBackend) -> None:
    async with backend.browser_context(account, headless=False) as context:
        page = await context.new_page()
        await page.goto(PERPLEXITY_URL, wait_until="domcontentloaded", timeout=60_000)
        print(f"\nOpened {PERPLEXITY_URL}")
        print("Log in manually in the opened browser window.")
        await asyncio.to_thread(input, "Press Enter here once you are logged in...")
        final_url = page.url
        print(f"Final URL after login: {final_url}")
        # Context exit persists storage_state automatically (CamoufoxBackend).
        await page.close()


async def _inspect(account: Account, backend: CamoufoxBackend) -> None:
    async with backend.browser_context(account, headless=False) as context:
        page = await context.new_page()
        await page.goto(PERPLEXITY_URL, wait_until="domcontentloaded", timeout=60_000)
        await asyncio.to_thread(
            input, "Navigate to the page/state you want to inspect, then press Enter..."
        )

        report = await page.evaluate(_DUMP_REPORT_JS)
        print("\n===== DOM REPORT =====")
        print(json.dumps(report, indent=2))

        await page.evaluate(_CAPTURE_INSTALL_JS)
        print("\n===== CLICK CAPTURE =====")
        print("Click elements to inspect them. Press Ctrl+C in this terminal to stop.")
        while True:
            info = await page.evaluate("window.__captured")
            if info is not None:
                print(json.dumps(info, indent=2))
                print("  suggested:", " | ".join(_suggest(info)))
                print("---")
                await page.evaluate("window.__captured = null")
            await asyncio.sleep(0.3)


def main() -> int:
    parser = argparse.ArgumentParser(description="Perplexity recon: login + selector capture.")
    parser.add_argument("--email", required=True, help="Account email to log in / inspect with.")
    parser.add_argument("--provider", default="perplexity", help="Provider name.")
    parser.add_argument("--data-dir", default=None, help="Override data directory.")
    parser.add_argument(
        "--inspect", action="store_true", help="Also run DOM report + click capture."
    )
    args = parser.parse_args()

    settings = Settings(data_dir=args.data_dir) if args.data_dir else Settings()
    manager = AccountManager(settings.paths, args.provider)
    try:
        account = manager.get(args.email)
    except AccountNotFoundError:
        account = manager.add(args.email)
        print(f"Registered new account {account.email}")

    backend = CamoufoxBackend(settings.paths, args.provider)
    if args.inspect:
        asyncio.run(_inspect(account, backend))
    else:
        asyncio.run(_login(account, backend))
    print("Session persisted. Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

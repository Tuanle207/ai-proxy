"""Extract and download generated images.

`RESULT_IMAGE_THUMBNAIL` is verified against a real, completed generation (see
`flowpage/selectors.py`). Each generated image appears twice in the DOM (main canvas +
agent chat log) with the same `src`, so `collect_image_urls` dedupes before slicing to `count`.
Verified `src` values are relative (e.g. `/fx/api/trpc/media.getMediaUrlRedirect?name=...`),
so `download_images` resolves them against the page's own URL before fetching.

`collect_existing_image_urls` snapshots every thumbnail URL currently on the page; when reusing
an existing (non-empty) Flow project, callers use this *before* submitting a new prompt so the
resulting baseline can be passed as `collect_image_urls`'s `exclude`, telling new results apart
from the project's prior generations.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from urllib.parse import urljoin

from playwright.async_api import Page

from ai_proxy.core.models import Artifact, TaskKind
from ai_proxy.providers.google_flow.page import selectors as sel


async def collect_image_urls(
    page: Page, count: int, *, exclude: frozenset[str] = frozenset()
) -> list[str]:
    thumbs = page.locator(sel.RESULT_IMAGE_THUMBNAIL)
    urls: list[str] = []
    for index in range(await thumbs.count()):
        src = await thumbs.nth(index).get_attribute("src")
        if src and src not in exclude and src not in urls:
            urls.append(src)
        if len(urls) >= count:
            break
    return urls


async def collect_existing_image_urls(page: Page) -> frozenset[str]:
    """Snapshot every (deduped) thumbnail URL currently on the page, unbounded."""
    thumbs = page.locator(sel.RESULT_IMAGE_THUMBNAIL)
    urls: set[str] = set()
    for index in range(await thumbs.count()):
        src = await thumbs.nth(index).get_attribute("src")
        if src:
            urls.add(src)
    return frozenset(urls)


async def download_images(
    page: Page, urls: list[str], output_dir: Path, *, timestamp: str
) -> list[Artifact]:
    """Download each image URL via the page's request context and save it locally.

    Filenames are `{timestamp}_{uuid4}.png` — `timestamp` is shared across one generation run,
    the uuid4 disambiguates multiple images from that same run. Interim (Phases 3–5): the
    artifact's `rel_path` holds the absolute download path; the runner/persistence layer
    re-roots it under `outputs_dir`.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    images: list[Artifact] = []
    for url in urls:
        absolute_url = urljoin(page.url, url)
        response = await page.context.request.get(absolute_url)
        content = await response.body()
        local_path = output_dir / f"{timestamp}_{uuid.uuid4().hex}.png"
        local_path.write_bytes(content)
        # Flow serves JPEG bytes regardless of the .png filename (see selectors.py); the true
        # format is sniffed again at persistence time via extract_image_metadata.
        images.append(
            Artifact(
                kind=TaskKind.IMAGE,
                mime="image/jpeg",
                source_url=url,
                rel_path=local_path,
                bytes=len(content),
            )
        )
    return images

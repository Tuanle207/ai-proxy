"""Image metadata extraction: real format sniffing, dimensions, size, sha256 (§6.8)."""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

_FORMAT_TO_CONTENT_TYPE = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
    "GIF": "image/gif",
}


@dataclass(frozen=True)
class ImageMetadata:
    bytes: int
    width: int | None
    height: int | None
    format: str | None
    sha256: str

    @property
    def content_type(self) -> str:
        return content_type_for(self.format)


def content_type_for(fmt: str | None) -> str:
    return _FORMAT_TO_CONTENT_TYPE.get(fmt or "", "application/octet-stream")


def extract_image_metadata(path: Path) -> ImageMetadata:
    """Sniff the true format with Pillow; Flow saves JPEG bytes under a `.png` name (§6.8)."""
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    fmt: str | None = None
    width: int | None = None
    height: int | None = None
    try:
        with Image.open(io.BytesIO(data)) as image:
            fmt = image.format
            width, height = image.size
    except Exception:
        pass  # non-decodable file: keep size/sha256, leave dims/format unknown
    return ImageMetadata(bytes=len(data), width=width, height=height, format=fmt, sha256=digest)

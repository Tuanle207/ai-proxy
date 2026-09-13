"""Resolution and creation of the on-disk data layout."""

from __future__ import annotations

import os
import stat
from pathlib import Path


def _ensure_private_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, stat.S_IRWXU)
    except OSError:
        pass
    return path


class DataPaths:
    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve()

    @property
    def api_key_file(self) -> Path:
        return self.root / "api_key"

    @property
    def outputs_dir(self) -> Path:
        return self.root / "outputs"

    @property
    def thumbnails_dir(self) -> Path:
        return self.root / "thumbnails"

    @property
    def assets_dir(self) -> Path:
        return self.root / "assets"

    @property
    def uploads_dir(self) -> Path:
        return self.root / "uploads"

    @property
    def providers_dir(self) -> Path:
        return self.root / "providers"

    def provider_dir(self, provider: str) -> Path:
        return self.providers_dir / provider

    def accounts_file(self, provider: str) -> Path:
        return self.provider_dir(provider) / "accounts.yaml"

    def sessions_dir(self, provider: str) -> Path:
        return self.provider_dir(provider) / "sessions"

    def session_dir(self, provider: str, email: str) -> Path:
        return self.sessions_dir(provider) / email.strip().lower()

    def storage_state_file(self, provider: str, email: str) -> Path:
        return self.session_dir(provider, email) / "storage_state.json"

    def ensure(self) -> None:
        _ensure_private_dir(self.root)
        _ensure_private_dir(self.providers_dir)
        _ensure_private_dir(self.outputs_dir)
        _ensure_private_dir(self.thumbnails_dir)
        _ensure_private_dir(self.uploads_dir)

    def ensure_session_dir(self, provider: str, email: str) -> Path:
        return _ensure_private_dir(self.session_dir(provider, email))

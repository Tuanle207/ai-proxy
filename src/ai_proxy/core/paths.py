"""Resolution and creation of the on-disk data layout (§2.6).

Provider-scoped state (account registries, browser session cookies) lives under
``providers/<provider>/``; outputs/thumbnails stay global.
"""

from __future__ import annotations

import os
import stat
from datetime import datetime
from pathlib import Path


def _ensure_private_dir(path: Path) -> Path:
    """Create a directory (if missing) and restrict it to the owner."""
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, stat.S_IRWXU)
    except OSError:
        pass  # best-effort; not all platforms (e.g. Windows) honor POSIX modes
    return path


class DataPaths:
    """Resolves the configurable data directory layout described in the requirement doc."""

    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve()

    # --- global ---

    @property
    def db_file(self) -> Path:
        return self.root / "ai-proxy.db"

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

    def job_output_dir(self, job_id: str, when: datetime) -> Path:
        """Per-job output directory `outputs/<yyyy-mm-dd>/<job_id>` (S-24)."""
        return self.outputs_dir / when.strftime("%Y-%m-%d") / job_id

    # --- provider-scoped (blocker 1.2.1 / 1.2.2) ---

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

    # --- creation ---

    def ensure(self) -> None:
        """Create the full directory tree, restricted to the current user."""
        _ensure_private_dir(self.root)
        _ensure_private_dir(self.providers_dir)
        _ensure_private_dir(self.outputs_dir)
        _ensure_private_dir(self.thumbnails_dir)

    def ensure_session_dir(self, provider: str, email: str) -> Path:
        return _ensure_private_dir(self.session_dir(provider, email))

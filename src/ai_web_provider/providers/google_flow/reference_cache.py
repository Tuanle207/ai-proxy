"""Per-workspace reference image upload cache.

Tracks which files (by sha256) have been uploaded to which Flow workspace for
which account, so that subsequent generations in the same reused workspace can
skip the browser file chooser step.

Stored as JSON at ``data/providers/google_flow/reference_cache.json``.

Schema::

    {
      "<sha256>": {
        "<account_email>": {
          "<workspace_ref>": "<uploaded_at_iso>"
        }
      }
    }
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import threading
from pathlib import Path
from typing import Any


class ReferenceCache:
    """Thread-safe JSON-backed cache of uploaded reference images per workspace."""

    def __init__(self, path: str | Path):
        self._path = Path(path)
        self._lock = threading.Lock()
        self._data: dict[str, dict[str, dict[str, str]]] = {}
        self._loaded = False

    def _load(self) -> None:
        if self._loaded:
            return
        if self._path.is_file():
            raw = self._path.read_text(encoding="utf-8")
            self._data = json.loads(raw) if raw else {}
        else:
            self._data = {}
        self._loaded = True

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._data, indent=2), encoding="utf-8")

    def is_uploaded(self, sha256: str, account_email: str, workspace_ref: str) -> bool:
        """Check whether a file has been uploaded to a workspace for an account."""
        with self._lock:
            self._load()
            accounts = self._data.get(sha256)
            if accounts is None:
                return False
            workspaces = accounts.get(account_email)
            if workspaces is None:
                return False
            return workspace_ref in workspaces

    def mark_uploaded(self, sha256: str, account_email: str, workspace_ref: str) -> None:
        """Record that a file was uploaded to a workspace for an account."""
        with self._lock:
            self._load()
            self._data.setdefault(sha256, {})
            self._data[sha256].setdefault(account_email, {})
            self._data[sha256][account_email][workspace_ref] = "now"
            self._save()

    def clear_workspace(self, account_email: str, workspace_ref: str) -> None:
        """Remove all cache entries for a workspace (e.g. after project deletion)."""
        with self._lock:
            self._load()
            changed = False
            for sha256, accounts in list(self._data.items()):
                workspaces = accounts.get(account_email)
                if workspaces and workspace_ref in workspaces:
                    del workspaces[workspace_ref]
                    changed = True
                if not workspaces:
                    del accounts[account_email]
                if not accounts:
                    del self._data[sha256]
            if changed:
                self._save()

    @staticmethod
    def compute_sha256(file_path: str | Path) -> str:
        """Compute sha256 of a file."""
        h = hashlib.sha256()
        h.update(Path(file_path).read_bytes())
        return h.hexdigest()

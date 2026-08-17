"""Atomic load/save of the accounts.yaml registry file."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import yaml

from ai_proxy.core.models import Account


def load_accounts(path: Path) -> dict[str, Account]:
    """Load accounts keyed by email. Returns an empty dict if the file is missing or corrupt."""
    if not path.is_file():
        return {}
    try:
        with path.open("r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}
    except yaml.YAMLError:
        return {}
    if not isinstance(raw, dict):
        return {}
    accounts: dict[str, Account] = {}
    for email, data in raw.items():
        try:
            accounts[email] = Account.model_validate(data)
        except Exception:
            continue  # skip corrupt entries rather than failing the whole load
    return accounts


def save_accounts(path: Path, accounts: dict[str, Account]) -> None:
    """Write the registry atomically (temp file + os.replace) to avoid corruption."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        email: yaml.safe_load(account.model_dump_json()) for email, account in accounts.items()
    }
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=".accounts-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            yaml.safe_dump(payload, fh, sort_keys=True)
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)

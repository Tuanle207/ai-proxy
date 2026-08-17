"""One-shot migration of the pre-refactor data layout to provider-scoped paths (Task 3.5).

Moves `data/accounts.yaml` + `data/sessions/` under `data/providers/google_flow/` so the
same email can hold independent per-site status/cookies (blockers 1.2.1 / 1.2.2).

Safety: existing logged-in sessions are expensive to recreate (manual + rate-limited login),
so each item is *copied*, verified (byte count), and only then removed from the source. The
script is idempotent — re-running it after a partial failure picks up where it left off.
The SQLite file (`flow.db` → `ai-proxy.db`) is NOT handled here; Phase 4's core v3 migration
owns the DB.

Usage:
    python scripts/migrate_data_layout.py [--data-dir data] [--provider google_flow] [--dry-run]
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
from pathlib import Path


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def migrate_file(src: Path, dst: Path, *, dry_run: bool) -> bool:
    """Copy `src` to `dst`, verify, then remove `src`. Returns True if action was taken."""
    if not src.is_file():
        return False
    if dst.is_file():
        print(f"  [skip] {dst} already exists")
        if _digest(src) != _digest(dst):
            print(f"  [WARN] {src} differs from {dst} — resolve manually before deleting either")
        return False
    print(f"  [move] {src} -> {dst}")
    if dry_run:
        return True
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    if _digest(src) != _digest(dst):
        print(f"  [FAIL] verify mismatch for {dst}; source kept at {src}")
        return False
    src.unlink()
    return True


def migrate_dir(src: Path, dst: Path, *, dry_run: bool) -> int:
    """Move each child of `src` into `dst` (copy + verify + remove, per child)."""
    if not src.is_dir():
        return 0
    moved = 0
    for child in sorted(src.iterdir()):
        target = dst / child.name
        if target.exists():
            print(f"  [skip] {target} already exists")
            continue
        print(f"  [move] {child} -> {target}")
        if dry_run:
            moved += 1
            continue
        if child.is_dir():
            dst.mkdir(parents=True, exist_ok=True)
            shutil.copytree(child, target)
            src_count = sum(1 for p in child.rglob("*") if p.is_file())
            dst_count = sum(1 for p in target.rglob("*") if p.is_file())
            if src_count != dst_count:
                print(f"  [FAIL] verify mismatch for {target}; source kept at {child}")
                continue
            shutil.rmtree(child)
        else:
            shutil.copy2(child, target)
            if _digest(child) != _digest(target):
                print(f"  [FAIL] verify mismatch for {target}; source kept at {child}")
                continue
            child.unlink()
        moved += 1
    return moved


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", default="data", help="Data directory root (default: data)")
    parser.add_argument("--provider", default="google_flow", help="Provider to scope under")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without moving")
    args = parser.parse_args(argv)

    root = Path(args.data_dir)
    provider_dir = root / "providers" / args.provider
    print(f"data dir: {root.resolve()}")
    print(f"provider dir: {provider_dir}")
    print(f"dry run: {args.dry_run}\n")

    print("accounts.yaml:")
    migrate_file(root / "accounts.yaml", provider_dir / "accounts.yaml", dry_run=args.dry_run)

    print("sessions:")
    moved = migrate_dir(root / "sessions", provider_dir / "sessions", dry_run=args.dry_run)
    print(f"moved {moved} session entr(y/ies)")
    src_sessions = root / "sessions"
    if not args.dry_run and src_sessions.is_dir() and not any(src_sessions.iterdir()):
        src_sessions.rmdir()  # empty: every child was verified + moved
        print(f"removed now-empty {src_sessions}")

    leftovers = (root / "sessions").is_dir() and any((root / "sessions").iterdir())
    if leftovers:
        print(f"\nNOTE: {root / 'sessions'} still has entries — resolve the WARN lines above.")
    print("\ndone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

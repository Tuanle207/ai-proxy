"""Import-contract guard (Phase 0.2 / Task 10.3).

Enforces the binding architectural rule from ADR-001: ``ai_proxy.core`` must never import
``ai_proxy.providers.*``, and sibling providers must never import each other.

Implemented as a dependency-free AST walk so it runs under plain ``pytest`` with no extra
tooling. Note: this contract is expected to *fail loudly* during Phases 1-4 while the Flow body
still lives behind core's ``worker/runner.py`` and ``worker/engine.py``; it becomes green at
Phase 5 and is wired into CI at Phase 10.3.
"""

from __future__ import annotations

import ast
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
_CORE = _SRC / "ai_proxy" / "core"
_PROVIDERS = _SRC / "ai_proxy" / "providers"


def _imported_modules(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return modules


def _py_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if p.name != "__pycache__")


def test_core_does_not_import_providers() -> None:
    violations: list[tuple[Path, str]] = []
    for path in _py_files(_CORE):
        for module in _imported_modules(path):
            # Only forbid specific provider modules (`ai_proxy.providers.<name>`). The bare
            # `import ai_proxy.providers` in `core/provider/registry.py` is the sanctioned
            # plugin-discovery hook, not a dependency on any provider's implementation.
            if module.startswith("ai_proxy.providers."):
                violations.append((path, module))
    assert not violations, (
        "core/ must not import ai_proxy.providers.* (ADR-001); violations:\n"
        + "\n".join(f"  {p}: {m}" for p, m in violations)
    )


def test_providers_do_not_import_siblings() -> None:
    if not _PROVIDERS.is_dir():
        return
    provider_dirs = [d for d in _PROVIDERS.iterdir() if d.is_dir()]
    violations: list[tuple[Path, str]] = []
    for provider in provider_dirs:
        for path in _py_files(provider):
            for module in _imported_modules(path):
                for other in provider_dirs:
                    prefix = f"ai_proxy.providers.{other.name}"
                    if other.name != provider.name and (
                        module == prefix or module.startswith(prefix + ".")
                    ):
                        violations.append((path, module))
    assert not violations, (
        "providers must not import sibling providers (ADR-001); violations:\n"
        + "\n".join(f"  {p}: {m}" for p, m in violations)
    )

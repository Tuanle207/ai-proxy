# Provider Authoring Guide

A provider is a plugin that teaches core how to drive one destination (e.g. Google Flow,
Perplexity). Core owns the queue, accounts, browser lifecycle, DB, events and HTTP surface; a
provider only knows how to operate one website. **Core never imports `ai_proxy.providers.*`** —
a provider self-registers and core resolves it by name.

## The ~6 files

A provider lives under `src/ai_proxy/providers/<name>/`:

| File | Purpose |
|------|---------|
| `params.py` | `class XParams(ProviderParams)` — per-request options (validated before submission). |
| `config.py` | `class XSettings(ProviderSettings)` — per-provider settings, `env_prefix="AI_PROXY_<NAME>_"`. |
| `adapter.py` | `class XAdapter` implementing `ProviderAdapter` (`execute`/`classify_failure`/`health_check`/`cleanup`). |
| `auth.py` | `class XAuth` implementing `AuthHandler` (login + logged-in probe). |
| `page/` | Site-driving helpers: `selectors.py`, `navigate.py`, `prompt.py`, `wait.py`, `extract.py`. |
| `__init__.py` | Build + `register()` the `ProviderSpec`. |

Optional: `db/schema.py` + `db/*_repo.py` (provider-owned tables, migrated under
`component="<name>"`), `api.py` (an `APIRouter` mounted at `/v1/providers/<name>`), `cli.py` (a
`typer.Typer` mounted as `aip <name-with-dashes>`).

## Skeleton

```python
# providers/<name>/__init__.py
from ai_proxy.core.models import TaskKind
from ai_proxy.core.provider.registry import register
from ai_proxy.core.provider.spec import Capabilities, ProviderSpec
from ai_proxy.providers.<name>.adapter import XAdapter
from ai_proxy.providers.<name>.auth import XAuth
from ai_proxy.providers.<name>.config import XSettings
from ai_proxy.providers.<name>.params import XParams

register(ProviderSpec(
    name="<name>",
    display_name="<Display Name>",
    capabilities=Capabilities(
        task_kinds=frozenset({TaskKind.TEXT}),
        max_outputs_per_request=1,
        supports_reference_inputs=False,
        supports_workspace_reuse=True,
        requires_browser=True,
    ),
    params_model=XParams,
    settings_model=XSettings,
    build_adapter=XAdapter,
    build_auth=XAuth,
))
```

The adapter is the one method that matters:

```python
class XAdapter:
    def __init__(self, deps: ProviderRuntimeDeps):
        self._deps = deps

    async def execute(self, session: ProviderSession, request: TaskRequest) -> TaskResult:
        page = session.page  # set because requires_browser=True
        ...  # drive the site; emit progress via session.emit; report a workspace via
             # session.on_workspace_created(ref)
        return TaskResult(request=request, account_email=session.account.email,
                          artifacts=[Artifact(kind=request.kind, mime="text/plain",
                                              text="answer", meta={"citations": [...]})],
                          workspace_ref=...)
```

Core hands you a live `ProviderSession` (account, `page` or `http`, `paths`, `output_dir`,
`settings`, `emit`, `on_workspace_created`); you return `Artifact`s and a `workspace_ref`. Core
persists artifacts, records success/failure, and calls `cleanup(session, workspace_ref)`.

## Selector discipline (the #1 maintenance cost)

Write every selector into `page/selectors.py` with a comment explaining *why* it is stable —
prefer backend-API path substrings, Material Symbols ligature text, or `role` attributes over
CSS class hashes (which are per-build and churn). Verify each selector against a **live** headed
session before trusting it; mark anything inferred-but-unverified with an explicit comment.
See `providers/google_flow/page/selectors.py` for the established convention.

## Rules

- Providers may import `core/` freely; they must **not** import sibling providers.
- Everything provider-specific that must be persisted goes into the opaque
  `TaskRequest.params` / `TaskResult.provider_state` JSON — never a new core column.
- Register on import; `providers/__init__.py` eagerly imports built-ins, and
  `registry.discover()` also loads third-party `ai_proxy.providers` entry points.
- Run `.venv\Scripts\python.exe -m ruff check src tests` and `mypy --strict src` before finishing.

# Architecture

`ai-proxy` is a multi-provider automation proxy: core owns the machinery, providers own the sites.
The authoritative, phase-by-phase plan is
[docs/multi-provider-refactor/multi-provider-refactor-plan.md](multi-provider-refactor/multi-provider-refactor-plan.md);
this file is the standing summary.

## Layout

```
src/ai_proxy/
├── cli/                # aip Typer root + per-concern command modules
├── core/               # provider-agnostic machinery
│   ├── config.py       # CoreSettings (AI_PROXY_*) + ProviderSettings base
│   ├── models.py       # Account, TaskKind, TaskRequest, Artifact, TaskResult, WorkspaceRef
│   ├── accounts/       # per-provider AccountManager (data/providers/<p>/accounts.yaml)
│   ├── browser/        # BrowserBackend protocol + Camoufox backend (per-provider cookies)
│   ├── db/             # SQLite engine, namespaced migrations, jobs/artifacts/events repos
│   ├── rotation/       # strategy, limiter, per-provider AccountSlotPool (+ shared semaphore)
│   ├── worker/         # EventBus, WorkerEngine (dispatch), TaskRunner, failure, recovery
│   ├── postprocess/    # generic image ops
│   ├── service/        # FastAPI app, container, routers (tasks/jobs/artifacts/events/ops/providers)
│   └── provider/       # THE SEAM: spec, params, adapter, auth, session, registry, runtime
└── providers/
    └── google_flow/    # page/, auth, params, config, adapter, db/, api, cli, spec
```

## The seam

- **`ProviderSpec`** — a declarative description (name, `Capabilities`, `params_model`,
  `settings_model`, `build_adapter`, `build_auth`, `migrations`, optional `api_router`/`cli_app`).
- **`ProviderAdapter`** — the one method that matters: `execute(session, request) -> TaskResult`.
- **`ProviderRegistry`** — `register`/`get`/`names`/`discover`; providers self-register on import.
- **`ProviderSession`** — what core hands an adapter: account, `page` (if `requires_browser`),
  `paths`, `output_dir`, `settings`, `emit`, `on_workspace_created`.

## Dependency rule

`core/` must never import `ai_proxy.providers.*` (enforced by
`tests/test_import_contract.py`). Providers import `core/` freely; siblings never import each
other. Provider-specific persistence goes in opaque `params`/`provider_state` JSON — never a new
core column.

## Request lifecycle

`POST /v1/tasks` → registry resolves the spec → validates `params` + `kind` → inserts a batch +
jobs → the `WorkerEngine` dispatch loop acquires a per-provider account slot → `TaskRunner`
builds a `ProviderSession` and calls `adapter.execute()` → artifacts are persisted and events
published over the SSE `EventBus`.

## On-disk layout

```
data/
├── ai-proxy.db
├── api_key
├── providers/<name>/accounts.yaml  +  sessions/<email>/storage_state.json
├── outputs/<yyyy-mm-dd>/job_<id>/
└── thumbnails/
```

# AI Proxy

Multi-provider automation proxy (Python library + CLI + service) around web AI apps, with
multi-account rotation. Core owns the machinery (queue, accounts, browser lifecycle, DB, events,
HTTP surface); each **provider** only knows how to drive one destination (Google Flow today).

See [docs/multi-provider-refactor/multi-provider-refactor-plan.md](docs/multi-provider-refactor/multi-provider-refactor-plan.md)
for the architecture and phased plan, and
[docs/multi-provider-refactor/provider-authoring-guide.md](docs/multi-provider-refactor/provider-authoring-guide.md)
for how to add a provider.

## Setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
python -m camoufox fetch   # one-time browser download
```

`ffmpeg` must be on `PATH` for the Google Flow watermark-overlay step.

## CLI

```powershell
aip --help
aip run --provider google_flow "a red apple on a wooden table" --count 2 -p aspect_ratio=16:9
aip run-batch --provider google_flow --prompts-file prompts.txt
aip accounts --provider google_flow add|remove|list|enable|disable|health|login
aip providers list | show <name>
aip doctor | aip config show | aip config path | aip serve
aip google-flow projects prune
```

`-p key=value` params are validated against the provider's params model before submission, so an
unknown or malformed param fails at the CLI instead of mid-job.

## REST + SSE service

```powershell
aip serve --host 127.0.0.1 --port 8080
# or via the dedicated console entrypoint:
ai-proxy-api
```

The API key is **always required** in `X-API-Key` (except `/healthz`): taken from
`AI_PROXY_API_KEY`, then `data/api_key`, otherwise generated + persisted on first start.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/v1/providers`, `/v1/providers/{name}` | Provider discovery + params schema. |
| `POST` | `/v1/tasks` | Submit a batch (`provider`, `kind`, `prompts[]`, `count`, `params{}`). |
| `GET` | `/v1/jobs`, `/v1/jobs/running`, `/v1/jobs/{id}` | Inspect jobs. |
| `POST` | `/v1/jobs/{id}/cancel` | Cancel a job. |
| `GET` | `/v1/batches/{id}`, `POST /v1/batches/{id}/cancel` | Batch status / cancel. |
| `GET` | `/v1/events` | SSE stream (filter `job_id`, `batch_id`, `types`; `Last-Event-ID` replay). |
| `GET` | `/v1/artifacts`, `/v1/artifacts/{id}`, `.../file`, `.../thumbnail` | Artifacts (text served inline). |
| `GET` | `/healthz`, `/readyz`, `/v1/accounts`, `/v1/stats` | Operations. |
| `*` | `/v1/providers/{name}/…` | Provider-supplied router (e.g. `google_flow/projects`). |

## Configuration

Settings come from `AI_PROXY_*` env vars or a YAML config file (`AI_PROXY_CONFIG_FILE`).
Per-provider settings use `AI_PROXY_<PROVIDER>_*` (e.g. `AI_PROXY_GOOGLE_FLOW_OVERLAY_LOGO=false`).
Key core settings: `AI_PROXY_PER_ACCOUNT_CONCURRENCY`, `AI_PROXY_MAX_CONCURRENT_BROWSERS`,
`AI_PROXY_API_KEY`, `AI_PROXY_DB_PATH`, `AI_PROXY_DEFAULT_PROVIDER`.

## Operational constraints

- **Single worker only** — the queue, slot pool, and account registry are process-local.
- While the service runs, mutate accounts through the service (`aip accounts` writes
  `accounts.yaml`; the service re-reads it when its mtime changes).
- Prompts and `metadata` are stored and echoed back **verbatim** — treat them as untrusted text.

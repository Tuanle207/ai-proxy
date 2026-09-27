# AI Web Provider

`ai-web-provider` is an in-process browser automation runtime for AI web
providers. It owns provider discovery, account persistence and rotation,
browser lifecycle, and provider-specific execution. It deliberately exposes no
HTTP server or API key configuration.

The public library surface is `ai_web_provider`:

```python
from ai_web_provider import ProviderExecutor, ProviderRuntimeContainer, Settings, TaskKind, TaskRequest

container = ProviderRuntimeContainer(Settings(data_dir="/var/lib/ai-provider-gateway/web-automation"))
await container.startup()
try:
    executor = ProviderExecutor(container)
    result = await executor.execute(TaskRequest(
        provider="perplexity",
        kind=TaskKind.TEXT,
        prompt="Explain the result",
        params={"model": "sonar-2"},
    ))
finally:
    await container.shutdown()
```

## Setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
python -m camoufox fetch
```

The runtime state lives below `Settings.data_dir`:

```text
providers/<provider>/accounts.yaml
providers/<provider>/sessions/<email>/storage_state.json
outputs/
```

The embedding application owns configuration. `Settings` accepts provider
settings through its `providers` mapping, such as `{"google_flow":
{"per_account_concurrency": 1}}`. One process must own a data directory at a
time because account state and browser sessions are persisted there.

Google Flow default-project reuse is serialized per account by default. The
runtime must return only artifacts created by the current generation; callers
should not enable it in production until its browser safety checks are verified.

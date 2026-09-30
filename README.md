# AI Web Provider

`ai-web-provider` is an in-process browser automation runtime for AI web
providers. It owns provider discovery, account persistence and rotation,
browser lifecycle, and provider-specific execution. One warm headless
ungoogled-chromium browser is shared by all providers; each task attempt restores
its account cookies into an isolated browser context and closes it afterward. It
deliberately exposes no HTTP server or API key configuration.

The public library surface is `ai_web_provider`:

```python
from ai_web_provider import ProviderExecutor, ProviderRuntimeContainer, Settings, TaskKind, TaskRequest

container = ProviderRuntimeContainer(Settings(
    data_dir="/var/lib/ai-provider-gateway/web-automation",
    providers={"perplexity": {"base_url": "https://www.perplexity.ai"}},
))
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
# Install a pinned ungoogled-chromium binary and pass its path explicitly.
```

The runtime state lives below `Settings.data_dir`:

```text
providers/<provider>/accounts.yaml
providers/<provider>/sessions/<email>/storage_state.json
outputs/
```

The embedding application owns all configuration. Construct `Settings` directly
with provider settings through its `providers` mapping, such as `{"google_flow":
{"projects_by_account": {"account@example.com": ["project"]}}}`. The library
does not read YAML files or environment variables. One process must own a data
directory at a time because account state and browser sessions are persisted there.
If the ungoogled-chromium binary needs process environment variables on the deployment
platform, supply them explicitly through `BrowserSettings.process_environment`.

The shared browser is closed after `BrowserSettings.idle_timeout_seconds` without
active job contexts. Interactive login uses a separate headed ungoogled-chromium
window at the configured stable viewport, then saves its verified cookies to that
account's `storage_state.json` file. Account-specific proxies are unsupported.

Google Flow default-project reuse is serialized per account by default. The
runtime must return only artifacts created by the current generation; callers
should not enable it in production until its browser safety checks are verified.

# Single Browser, Per-Job Context Design

## Status

Proposed.

## Summary

Run one long-lived Camoufox browser for each started
`ProviderRuntimeContainer`. For every execution attempt, create a new isolated
Playwright `BrowserContext`, run the provider work in a page within it, and
close the page and context before that attempt finishes. Persist the account's
provider-scoped storage state when the context closes.

The shared browser must launch with `block_images=True`.

This replaces the current warm-session model, which retains a browser and
context per account for `browser_idle_ttl_seconds` after a job completes.

## Goals

- Launch exactly one `AsyncCamoufox` browser for a started runtime container.
- Create a distinct `BrowserContext` for every job attempt.
- Close every job context immediately after its page work completes, including
  on failure or cancellation.
- Persist login state in the existing provider/account `storage_state.json`
  file, rather than retaining it in an idle browser context.
- Launch Camoufox with `block_images=True`.
- Keep current account selection, retry policy, provider adapters, and output
  handling unchanged.

## Non-Goals

- Adding a queue, worker process, HTTP API, or job scheduler.
- Reusing contexts, pages, cookies, local storage, or service workers in
  memory between jobs.
- Changing account rotation or account-failure classifications.
- Supporting per-account proxy or GeoIP configuration.
- Automatically restarting a disconnected shared browser.

## Current Architecture

`ProviderRuntimeContainer` constructs one `CamoufoxBackend` for every
provider. `ProviderExecutor.execute()` obtains an account slot, enters
`backend.browser_context(...)`, creates a page, calls the provider adapter, and
closes that page in a `finally` block.

With the default `browser_idle_ttl_seconds=600`, `CamoufoxBackend` currently
keeps a warm `AsyncCamoufox` browser and its `BrowserContext` alive per account
after a job returns. The backend tracks active pages, per-account warm-session
locks, idle-eviction tasks, and optional tab sharing. The warm context is
closed only after idle eviction or container shutdown.

The resulting topology is:

```text
ProviderRuntimeContainer
  provider backend
    account warm session -> AsyncCamoufox -> Browser -> BrowserContext -> Page
```

This retains job state longer than necessary and permits multiple browser
processes in one runtime container.

## Target Architecture

The runtime container owns one browser process. Provider-specific backends
continue to own provider/account storage-state paths and context setup, but do
not own browser launch or warm-context pooling.

```text
ProviderRuntimeContainer
  SharedCamoufoxBrowser -> AsyncCamoufox -> Browser
  provider backend
    job attempt -> BrowserContext -> Page
```

The only session data that survives a job is the storage state persisted at:

```text
providers/<provider>/sessions/<email>/storage_state.json
```

## Lifecycle

### Startup

`ProviderRuntimeContainer.startup()` must:

1. Build the container-level Camoufox launch options.
2. Construct and enter one `AsyncCamoufox` context manager.
3. Retain its Playwright `Browser` object for all provider backends.
4. Mark the container ready for execution.

The launch options include:

```python
{
    "headless": settings.headless,
    "humanize": True,
    "block_images": True,
    "window": (settings.browser_window_width, settings.browser_window_height),
}
```

`window` is omitted when either configured dimension is absent.

`startup()` must be idempotent: a second successful call must not launch a
second browser.

`headless` is browser-scoped. `AI_PROXY_HEADLESS=false` is required for
interactive login, and all jobs use that same headful browser until shutdown.
When `AI_PROXY_HEADLESS=true`, interactive-login methods fail before opening a
page and instruct the operator to restart with `AI_PROXY_HEADLESS=false`.

### Job Attempt

For each retry attempt in `ProviderExecutor.execute()`:

1. Acquire an eligible account slot.
2. Resolve the selected account.
3. Create a new browser context from the shared browser.
4. Load that provider/account's persisted storage state if it exists.
5. Create one page in the context.
6. Execute the provider adapter with `ProviderSession`.
7. Close the page in the executor's existing `finally` block.
8. Atomically persist the context storage state.
9. Close the context in a `finally` block.
10. Record account success or apply existing failure effects.
11. Release the account slot.

The context closes before the attempt returns or raises. A retry always gets a
new context and cannot inherit in-memory state from the failed attempt.

### Shutdown

The embedding application remains responsible for shutdown ordering:

1. Stop accepting new jobs.
2. Drain or cancel active `ProviderExecutor.execute()` calls.
3. Await `ProviderRuntimeContainer.shutdown()`.

Container shutdown must close any still-active contexts as a defensive
fallback, then exit the single retained `AsyncCamoufox` context manager.
`shutdown()` must be idempotent.

The shared browser must not be closed during normal active work. Closing it
invalidates every active context, so callers must drain work first.

## Context Ownership and Cleanup

`CamoufoxBackend.browser_context()` remains the provider-facing async context
manager. It changes from choosing or launching a warm session to creating one
fresh context from the shared browser.

Its cleanup ordering is:

1. Persist context storage state under the existing per-account write lock.
2. Close the context even if persistence fails.
3. Re-raise persistence errors after context cleanup, subject to the existing
   execution failure policy.

The executor remains responsible for closing the primary page before exiting
the backend context manager. Closing the context also closes any unexpected
remaining pages opened by adapter code.

## Removed Warm-Session Behavior

The following warm-pooling mechanisms are removed:

- `_WarmSession`.
- `_warm` and `_warm_locks`.
- `active_pages` and `max_tabs_per_session` sharing.
- Idle-eviction tasks and `browser_idle_ttl_seconds` behavior.
- `close_account_sessions()` and all warm-context cleanup operations.

`close_all()` remains as defensive shutdown cleanup for active contexts.

Provider-specific `max_tabs_per_session` settings are no longer meaningful.
`browser_idle_ttl_seconds` is removed because no context remains idle after a
job. Existing deployment configuration using these values must be removed or
ignored only as a deliberate compatibility decision.

## Image Blocking

`block_images=True` is a launch-level Camoufox option and is applied once to
the shared browser. It prevents normal page image-resource loading and should
reduce bandwidth, memory use, and rendering overhead.

Google Flow produces image artifacts, so real-browser verification is required
before rollout. The expected artifact path uses explicit context requests for
download after the output URL is found. If image blocking prevents those
explicit downloads, use a dedicated artifact-download path rather than
disabling image blocking or keeping contexts alive.

## Proxy and GeoIP Decision

Per-account proxy and GeoIP behavior are out of scope. The current launch
options only include `proxy` and `geoip=True` when an account has a proxy; that
is incompatible with one shared browser and is not needed for this deployment.

The new shared-browser launch configuration must omit account-specific
`proxy` and `geoip`. Accounts with configured proxies are rejected when a job
attempt opens its context. The implementation must not silently create an
additional browser to accommodate a proxy-configured account.

## Concurrency

Account-slot pools remain the admission-control mechanism. Multiple admitted
jobs may concurrently create separate contexts in the one browser, subject to
the existing global and per-account limits.

Every job gets a unique context. No pages, cookies, local storage, cache, or
service workers are shared in memory across jobs.

Storage-state persistence remains serialized per provider/account. Concurrent
contexts for the same account can still produce last-writer-wins state, so
providers with mutable session state should retain per-account concurrency of
one. Google Flow already defaults to that limit.

## Failure Handling

- Page closure remains guaranteed by `ProviderExecutor.execute()`.
- Context closure is guaranteed even if adapter execution, page closure, or
  storage-state persistence fails.
- Account-slot release remains guaranteed by the executor's outer `finally`.
- A disconnected shared browser causes context creation to fail through the
  existing browser-error retry and account-effect path.
- A shared-browser failure affects all concurrent jobs, which is the accepted
  tradeoff for the one-browser requirement.

Automatic browser relaunch is intentionally not included in this change. Its
recovery semantics, synchronization, and in-flight-job behavior require a
separate design.

## Implementation Changes

### `runtime/container.py`

- Add ownership of the one shared `AsyncCamoufox` lifecycle.
- Make `startup()` launch the browser and expose it to all provider backends.
- Make `shutdown()` close remaining active contexts and exit the shared
  Camoufox context manager.
- Stop constructing independently launch-capable browser backends per provider.

### `core/browser/camoufox_backend.py`

- Replace warm-session pooling with fresh context creation from an injected
  shared browser.
- Retain provider/account storage-state loading and atomic persistence.
- Remove per-account browser launch, proxy/GeoIP launch options, warm locks,
  idle eviction, and tab-sharing logic.
- Ensure context close runs even when storage persistence fails.

### `core/browser/base.py`

- Simplify the browser-backend protocol to context creation and any required
  shared-browser lifecycle collaboration.
- Remove warm-session-specific methods when their callers are removed.

### `core/config.py`

- Add no new image-blocking setting: image blocking is required and always on.
- Remove `browser_idle_ttl_seconds` and warm-session-only settings.
- Use `max_concurrent_jobs` as the cap on in-flight jobs and active contexts.

### Tests and Documentation

- Update unit fakes for one shared browser and per-job contexts.
- Remove warm-session and idle-eviction tests.
- Update the README lifecycle description and gateway integration design.

## Verification

### Unit Tests

- `startup()` launches Camoufox exactly once.
- Two sequential jobs use the same browser and two different contexts.
- Permitted concurrent jobs use unique contexts.
- A successful job closes its page and context.
- An adapter failure closes its page and context, then releases its account
  slot.
- Cancellation closes the context and releases the slot.
- Context closure still occurs when storage persistence raises.
- Storage-state paths remain provider/account scoped and writes remain atomic.
- `shutdown()` exits the shared browser exactly once.
- Camoufox launch options include `block_images=True` and omit proxy/GeoIP.

### Integration Tests

- Execute multiple sequential provider jobs and verify one Camoufox process is
  launched.
- Verify an authenticated account restores state in a new context on the next
  job.
- Verify no contexts or pages remain after each completed job.
- Verify a Google Flow generation can discover and download its output with
  image blocking enabled.
- Verify graceful application shutdown after active work drains.

## Acceptance Criteria

- A started `ProviderRuntimeContainer` owns one `AsyncCamoufox` browser.
- Browser contexts are never reused between job attempts.
- Every job context closes before execution returns or raises.
- The browser is retained until container shutdown, not until an idle TTL
  expires.
- Camoufox starts with `block_images=True`.
- No per-account proxy or GeoIP browser behavior remains.
- Existing account-slot release, retries, and account state updates continue to
  work.
- Google Flow output downloads remain functional with image blocking enabled.

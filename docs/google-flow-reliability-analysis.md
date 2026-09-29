# Google Flow automation — reliability analysis (log of 2026-09-28 16:10–16:21)

## 1. Summary

3 image jobs were submitted at the same time (4 accounts, 1 slot per account). All 3 eventually
succeeded, but it took **7 attempts**, and one job needed **~11 minutes** and 3 accounts.

| Attempt | Job (prompt) | Account / project | Outcome | Time lost |
|---|---|---|---|---|
| A1 | "cozy cabin" (39) | intomorrow / `6b93…` | `model_not_found` → submitted anyway → **no completion after 360 s** | 6 min 30 s |
| B1 | "robot painting" (40) | letgo / `54ec…` | **`tune` button not visible after 60 s** | 70 s |
| C1 | "boy + cat" (36) | themilkyway / `3d82…` | **`tune` button not visible after 60 s** | 66 s |
| C2 | "boy + cat" | tuanle2x7 / `8851…` | OK (72 s) | — |
| B2 | "robot painting" | themilkyway / `3d82…` | OK (127 s, incl. ~30 s waiting for an account) | — |
| A2 | "cozy cabin" | tuanle2x7 / `2a2c…` | settings panel **did not open**; model/aspect/count each waited 30 s, then Save click failed | 1 min 42 s |
| A3 | "cozy cabin" | letgo / `54ec…` | OK (151 s) | — |

First-attempt success rate: 0/3. Every attempt succeeded on a retry, so these were
**transient page/UI-state failures, not account or quota problems**. Even so, each failure put a
healthy account on cooldown.

## 2. Failure analysis

### F1. Settings (`tune`) button never became visible — B1, C1
- `configure_generation` → `page.locator(SETTINGS_BUTTON).first.wait_for(visible, 60s)`
  (`page/params.py:29`).
- B1 and C1 failed within 1 s of each other, ~62 s after they started. At that point 3 Camoufox
  contexts were loading Flow at the same time on the VM (aarch64 instance).
- Both accounts worked on the next attempt (same projects, 1–6 min later).
- Before this step, the only readiness check is `wait_for_load_state("domcontentloaded")` plus a
  URL check in `_navigate_to_project` (`page/navigate.py:163`). On an SPA, `domcontentloaded`
  tells us nothing about whether the app has rendered.
- **Cause is not provable from the logs** because no screenshot or DOM was captured. Likely
  candidates, in order:
  1. The SPA was still loading or hydrating under CPU contention from 3 concurrent browsers.
  2. A modal/overlay (first-run onboarding, "what's new", consent) hid the prompt bar. letgo and
     themilkyway were created about 15 minutes earlier (`success_count=0`).
  3. The page landed in a non-standard state, e.g. a project error or a different layout.

### F2. Settings panel did not open after clicking `tune` — A2
- The `tune` button was found and clicked with `force=True`, but none of `flow-settings-view` or
  `flow-toggles` appeared. `set_model`, `set_aspect_ratio` and `set_count` each waited for the
  **default 30 s Playwright timeout** (their `inner_text()` calls have no timeout), and each
  swallowed the `TimeoutError`. Then `_save_and_close` failed after 5 s. Total: about 95 s wasted
  on a panel that was clearly closed from the start.
- `force=True` skips actionability checks. If an overlay was covering the button, the click
  "succeeds" without doing anything.
- Project `2a2cc887…` is tuanle2x7's second project, and it is only used because of round-robin.
  That account's history is `success_count=7, fail_count=12`. Some projects may be consistently
  unhealthy, and nothing tracks this today.

### F3. Generation never completed within 360 s — A1
- In `wait_for_completion` (`page/wait.py:34`), the stop button stayed visible and the first
  tile's `data-media-id` never changed for 6 minutes. Successful generations in the same window
  took 60–140 s.
- `set_model` had logged `google_flow_model_not_found` for "Nano Banana 2", but the job continued
  with **whatever model Flow had selected**. That could be a slower model, a quota-limited one,
  or one that fails in a way the wait loop cannot see.
- The wait loop only knows 2 terminal signals: "stop hidden and new media id", or deadline. It
  has no fast path for:
  - submission never registered (the stop button never appeared),
  - generation failed inside the tile (policy, safety or "something went wrong" rendered in the
    grid, not as `[role='alert']`),
  - generation stalled (no progress for N seconds).
- At the deadline, `[role='alert']` was not found, and this was logged as a full exception
  traceback (`google_flow_error_banner_read_failed`) that is only noise.

### F4. `model_not_found` although the model exists — A1
- A2, B2 and A3 later found or selected "Nano Banana 2", so the option exists.
- In `set_model` (`page/params.py:51-63`), `items.count()` does **not auto-wait**. If the dropdown
  container is visible but its items haven't rendered yet, the loop runs 0 times and reports
  "not found".
- The label parse `text.strip().split(maxsplit=1)[1]` assumes an icon-ligature prefix. Any
  label without one raises `IndexError`, which is not caught (only `PlaywrightTimeoutError` is).
- A missing model is logged as an error but not acted on, so artifacts may come from a
  different model than the caller requested, with no indication in the result.

### F5. Account penalties for non-account failures
- Neither `GoogleFlowAdapter.classify_failure` (`adapter.py:142`) nor
  `default_classify_failure` (`core/failure.py:39`) handles Playwright `TimeoutError`, so it
  becomes `browser_error` → `AccountEffect.COOLDOWN`, and `GenerationTimeoutError` also becomes
  `COOLDOWN`.
- Result: at 16:12:09, 3 of 4 accounts were in `cooldown` because of UI flakiness. Job B sat
  waiting for an account (`account_slot_wait_no_candidate`) even though nothing was wrong with
  any of them.
- Retries always move to another account and reload a new context. No cheap **same-page
  recovery** exists (reload plus retrying the step), even though every failure here was
  transient.

### F6. Latent bugs visible in the tracebacks
- **`existing_image_urls=frozenset()` in every attempt**, including projects that already had
  images. `collect_existing_image_urls` runs right after `goto` (`adapter.py:75`), before the grid
  renders, so the baseline used to exclude old images is empty. Right now, correctness depends
  only on the new image being the first tile. If a generation fails and the loop ever exits
  "successfully", an **old image would be returned as the new result**.
- `wait_for_completion` reads `current_latest_media_id` with `.first.get_attribute(...)` and no
  timeout. On an empty project this blocks for 30 s and then raises.
- `AccountManager._mutate_success` never resets `status=COOLDOWN` back to `ACTIVE`. For example,
  tuanle2x7 shows `status=COOLDOWN` with `cooldown_until` set to 00:59, hours in the past.
  Availability is still correct, but `account_statuses` in logs is misleading.

### F7. Observability gaps
- No request or job id appears in the log lines. Attempts can only be matched to jobs through
  `prompt_chars`.
- The executor does not log the attempt number, the classified `error_code`, or the
  `account_effect`.
- No screenshot or HTML is captured on failure, which is why F1 and F2 can't be root-caused.
- Rich tracebacks with `show_locals` dump the full `GoogleFlowSettings` (all emails and project
  ids) for every error, about 300 lines each, and bury the useful information.
- No per-step timings are logged, so there is no data on how long page load, configure, submit
  and generation each took.

## 3. Recommendations (prioritised)

### P0 — make failures diagnosable (do this first)
1. **Capture failure evidence on every failed attempt**: screenshot, HTML, console output and
   metadata. It is always on, has no setting, and does nothing when an attempt succeeds. Full
   design in §4.
2. **Add an end-to-end `request_id`.** The gateway creates it and passes it through
   `TaskRequest`. The executor binds `request_id`, `attempt`, `provider` and `account_email` into
   structlog's shared log context (`bind_contextvars`). The adapter adds `step` and
   `workspace_ref`. See §4.3.
3. In the executor, log `attempt_failed` with `attempt`, `error_code`, `account_effect`,
   `retryable` and `capture_id`.
4. Configure logging explicitly in the gateway. Today it never calls `configure_logging`, so
   structlog's defaults (rich tracebacks with `show_locals=True`) end up in production logs.
5. Log per-step durations (`step`, `elapsed_ms`).

### P0 — headless-specific checks
The service runs headless, so screenshots are the only way to see the page. Headless mode is also
a suspect in its own right:
- Check that `browser_window_width/height` (1280×720 in `core/config.py:84`) actually reaches
  `browser.new_context(...)` in `camoufox_backend.py:67`. That call passes no viewport today, so
  the size may come from Camoufox's random fingerprint instead. Flow's layout changes with
  window size. Pin a known-good viewport (e.g. 1920×1080) and confirm it from the failure
  screenshots.
- All jobs share one browser process, and headless runs usually render in software without a
  GPU, so bursts compete for CPU (see item 19).
- A/B test: run the same 3-job burst headless and headed under Xvfb (a virtual display). If the
  headed run passes consistently, the cause is rendering or window size, not timing.

### P1 — fail fast and recover in place
6. **Explicit "app ready" gate after navigation.** Replace `domcontentloaded` with waiting for the
   prompt textbox (`PROMPT_TEXTBOX`) **and** the `tune` button, with a shorter timeout (e.g.
   20 s). On timeout, `page.reload()` once and wait again before failing.
7. **Dismiss known overlays** before interacting: close any visible `[role='dialog']` or
   `cdk-overlay` with Escape or its close button, then log what was dismissed. Use the screenshots
   from (1) to build the list of real dialogs.
8. **Verify the settings panel actually opened.** After clicking `tune`, wait for
   `flow-settings-view` to be visible (5–10 s). If it isn't, press Escape, click again without
   `force` (so Playwright surfaces the covering element), and fail with a clear error
   (`SettingsPanelNotOpenError`) instead of running 3 × 30 s of blind setters.
9. **Explicit short timeouts on every locator read** in `params.py` (`inner_text(timeout=3000)`).
   Never rely on the 30 s default.
10. **Fix model selection:**
    - wait for `flow-menu-item` to be visible before `count()`;
    - match by `has_text` or a normalised `endswith` instead of `split(maxsplit=1)[1]`;
    - on miss, log the options that *were* found;
    - after selection, re-read the trigger label to confirm;
    - if the requested model can't be selected, **fail the attempt** (or try
      `model_fallback_order` explicitly) and record the actual model in the result instead of
      silently generating with the default.
11. **In-adapter step retry.** Wrap `open_project → configure_generation` in a small loop (max 2):
    on Playwright timeout, reload and retry on the **same page and account**. Every failure in
    this log would likely have been recovered this way without a context switch or cooldown.

### P1 — smarter completion detection
12. **Submission confirmation.** After clicking submit, wait up to ~15 s for the stop button to
    appear (or for a new pending tile). If neither appears, the submit did not register: retry
    the click once, then fail fast. Don't wait 360 s.
13. **Stall and failure detection in the wait loop:**
    - detect error or failed tiles in the grid, not only `[role='alert']`;
    - add a no-progress watchdog, e.g. fail if still running after ~2.5× the observed p95
      (~150 s → ~240 s) instead of the flat 360 s;
    - check the error banner with `count() > 0` instead of `text_content(timeout=2000)` to avoid
      the exception-plus-traceback noise.
14. **Consider network-level signals** (medium term). Listen with `page.on("response")` for
    Flow's generate or media API responses. HTTP status and error payloads are more reliable
    than DOM polling, and they reveal quota or safety errors directly. The endpoint names must be
    discovered live first.

### P1 — don't punish healthy accounts
15. Implement `GoogleFlowAdapter.classify_failure`:

    | Exception / step | retryable | account effect |
    |---|---|---|
    | Playwright `TimeoutError` in `open_project` / `configure_generation` / `submit_prompt` | yes | **NONE** (or 1 min soft cooldown) |
    | `SettingsPanelNotOpenError`, submit not registered | yes | NONE |
    | `GenerationTimeoutError` with no error text | yes | short cooldown (1–2 min) |
    | Banner or tile text matching quota/credit | yes | QUOTA / MODEL_QUOTA cooldown |
    | Redirect to `accounts.google.com` | yes | NEEDS_LOGIN |

16. **Track project health separately from account health.** Record failures per `project_id` in
    `GoogleFlowProjectPool`, skip a project after N consecutive UI failures (e.g. project
    `2a2cc887…`), and log it for manual inspection.
17. Reset `status` to `ACTIVE` in `_mutate_success` when `cooldown_until` has passed.

### P2 — correctness and capacity
18. **Fix the baseline for new-image detection.** Take the `existing_image_urls` / media-id
    snapshot **after** the app-ready gate (6), when the grid has rendered. Prefer media-id diffs
    (`data-media-id` set before vs after) over "first tile" ordering. Use `count()` with a
    fallback to `None` for empty projects instead of `.first.get_attribute()`.
19. **Stagger concurrent starts and verify VM headroom.** Both F1 failures happened while 3
    browsers loaded Flow at once; later 2-at-a-time runs were all fine. Add 5–10 s jitter between
    job starts, monitor CPU and RAM during bursts, and cap concurrency to what the VM sustains.
20. **Overall deadline budget.** Pass one deadline through all steps (navigation + configure +
    wait) and across retries, so a request can't take 3 × (60 + 90 + 360 s) in the worst case.
21. **Warm-up / health check for new accounts.** Open Flow once per new account and project,
    dismiss first-run dialogs, and confirm the prompt bar and settings panel work before putting
    the account into rotation.

## 4. Failure capture design (always on, errors only)

> **Status: implemented** in ai-web-provider (`core/diagnostics.py`, `runtime/executor.py`) and
> ai-provider-gateway (`observability.py`, `api/app.py`). Differences from the design below:
> - Adapters mark steps with `step = mark_step("...")`, which binds `step` into the log context
>   and records the step's timing.
> - There is no separate prune at start-up. Pruning runs on the first capture after start-up and
>   then at most once an hour.
> - The gateway's chat route logs failures with their `capture_ids` but keeps its existing
>   502 + message response.

### 4.1 Behaviour
- There is **no setting** to turn capture on or off. Every failed attempt is captured, and
  successful attempts cost nothing: no tracing or recording runs while the job is healthy.
- Capture runs in **`ProviderExecutor.execute`** (`runtime/executor.py`), in the `except` block,
  **before** `page.close()`, while the page still shows the failing state. Because it lives in the
  executor rather than the adapter, Perplexity and future providers get it too.
- It is **best-effort and bounded**. The whole capture is wrapped in
  `asyncio.wait_for(..., timeout=10s)`, and every sub-step has its own `try` block. A capture
  failure is logged as a warning and never replaces or hides the original exception.
- A small new module, `core/diagnostics.py`, holds one function:
  `capture_failure(page, error, meta) -> str | None`. It returns a `capture_id`.

### 4.2 What is captured
Each capture goes in `<data_dir>/failures/<YYYY-MM-DD>/<capture_id>/`, where
`capture_id = <HHMMSS>_<request_id>_a<attempt>`:

| File | Source | Purpose |
|---|---|---|
| `screenshot.png` | `page.screenshot(full_page=True, timeout=5000)` | what the headless page looked like |
| `page.html` | `page.content()` | check selectors offline (e.g. is `tune` in the DOM but hidden or covered?) |
| `meta.json` | executor | see below |

`meta.json` contains:
- ids: `request_id`, `attempt`, `provider`, `account_email`, `workspace_ref`
- `step`, taken from the adapter's bound log context
- `page_url` and viewport size
- error details: `error_type`, `error_message`, `error_code`, `account_effect`, `retryable`, and
  the formatted traceback **without locals**
- request details: `prompt_chars` and `params` (model, aspect ratio). The prompt text is not
  stored.
- `console` and `page_errors`: the last ~50 entries, from a ring buffer
- `failed_requests`: the last ~20 responses with status ≥ 400, plus `requestfailed` events (URL
  and status only, no bodies)
- `step_timings`: per-step durations

The console and network buffers are cheap listeners attached when the page is created in the
executor (`page.on("console" | "pageerror" | "requestfailed" | "response")`). They are only
written to disk when the attempt fails.

The storage-state/cookie file is not captured, and **response bodies are never stored**.

Playwright tracing (`context.tracing`) is deliberately **not** used by default. It would have to
record every attempt just to keep the failed ones, which adds CPU load during exactly the bursts
that fail (see F1). Reconsider it only if screenshot + HTML + console turn out not to be enough.

### 4.3 Changes in ai-web-provider
1. `TaskRequest.request_id: str | None = None`. If it is missing (CLI use), the executor generates
   `req_<uuid8>`.
2. `DataPaths.failures_dir` = `<root>/failures`, created as 0700 in `ensure()`. It holds
   screenshots of logged-in Google pages, so it must stay private.
3. Executor:
   - binds `request_id`, `attempt`, `provider` and `account_email` into the shared log context;
   - attaches the listeners;
   - on error, calls `capture_failure` and then logs `attempt_failed` with the `capture_id`;
   - records per-attempt outcomes in `attempts: list[AttemptRecord]`, where each record holds
     `attempt`, `account_email`, `step`, `error_code` and `capture_id`.
4. Adapters (Google Flow now, Perplexity later) call `bind_contextvars(step=..., workspace_ref=...)`
   at every step change, alongside the existing `step = "..."` assignments. The executor then
   reads `step` back from the log context, so no exception type has to change.
5. The final outcome carries the attempt history:
   - On success: `TaskResult.attempts`, so captures from attempts that failed before a later
     success can still be linked.
   - On failure: raise `TaskFailedError(AIProxyError)` with `request_id`, `attempts` and
     `last_error_code`, chained to the original exception (`raise ... from last_error`). The
     gateway already catches generic `Exception`, so nothing breaks.
6. Retention: `prune_failures(max_age_days=7, max_total_mb=500)` runs at runtime-container
   start-up and after each capture (at most once an hour). These are fixed defaults in
   `Settings`, not an enable switch.

### 4.4 Integration with ai-provider-gateway
The gateway runs ai-web-provider as the `vendor/ai-web-provider` git submodule, not from this
checkout, so every change above must be followed by a submodule bump.

1. **Request id middleware** (`api/app.py`):
   - accept an incoming `X-Request-ID` if it is valid (≤ 64 chars, `[A-Za-z0-9_-]`), otherwise
     generate `req_<uuid>`;
   - bind it into the shared log context with `bind_contextvars`, and clear it at the end of the
     request;
   - return it in the `X-Request-ID` response header on every response, errors included.
2. **Pass it down:** `WebGoogleFlowImageAdapter.generate`
   (`integrations/web_google_flow/adapter.py`) sets `TaskRequest(request_id=...)`. Do the same for
   the Perplexity chat adapter.
3. **Logging:** call `configure_logging(level, json=...)` in the lifespan function, using a new
   `AI_PROVIDER_GATEWAY_LOG_JSON` env var (default: console). Build the console renderer with
   `show_locals=False`. This removes the ~300-line tracebacks that dump settings.
4. **Stop swallowing errors** in `/v1/images/generations` (`app.py:214-217`):
   - log `image_generation_failed` with `request_id`, `error_code` and `capture_ids` (from
     `TaskFailedError.attempts`);
   - add `request_id` to the error body, map the error to a meaningful `code`, and use a correct
     `type` (today it is always `invalid_request_error`):

   | Final error | HTTP | `code` |
   |---|---|---|
   | `NoAvailableAccountError` | 503 | `no_available_account` |
   | `QuotaExceededError` | 429 | `provider_quota_exceeded` |
   | `GenerationTimeoutError` | 504 | `provider_timeout` |
   | `AuthError` | 503 | `provider_auth_required` |
   | anything else | 502 | `provider_error` |

   File paths and capture contents are **never** returned to API clients. They only get the
   `request_id`.
5. **Operator access:**
   - *Phase 1:* on the VM, `grep <request_id> $STATE_DIR/ai-provider-gateway.log` shows
     `attempt_failed ... capture_id=...`. Then copy the files off the VM with
     `scp -r vm:$STATE_DIR/web-automation/failures/<date>/<capture_id> .`
   - *Phase 2 (optional):* a `GET /v1/admin/failures?request_id=` endpoint that lists captures,
     plus `GET /v1/admin/failures/{capture_id}/{file}`. Both require a separate admin API key and
     are not mounted when that key is unset.
6. **Deployment:** `deploy.sh` makes sure `$STATE_DIR/web-automation/failures` exists with owner
   `ai-provider-gateway` and mode 0700. The app does its own pruning, so logrotate is not
   needed. Document the directory and the lookup flow in the deployment README.
7. **Consumers** (e.g. english-podcast-creator): log the `X-Request-ID` / `error.request_id` of
   any failed image call, so a user-visible failure can be traced to the capture.

### 4.5 Verification
- Unit test (ai-web-provider): a fake adapter raises at a known step, and the test checks that
  `meta.json` exists with the right `request_id`, `attempt` and `step`, that `screenshot.png`
  exists, and that the original exception type still propagates.
- Unit test: capture itself fails (page already closed); the original error still propagates and
  a warning is logged.
- Unit test: a successful attempt writes nothing to `failures/`.
- Unit test: pruning honours the age and size limits.
- Gateway test: an `X-Request-ID` round-trip, and a 5xx body containing `request_id` and the
  mapped `code`.
- Live: re-run the 3-job burst on the VM. Every `google_flow_step_failed` must have a matching
  capture folder, found only by grepping the `request_id` returned to the client.

## 5. Suggested implementation order

1. §4 (failure capture + request id, ai-web-provider then gateway + submodule bump): deploy and
   reproduce the 3-job burst.
   → verify: every failure has a capture, and it can be found from the client-visible
   `request_id`.
2. Items 6, 8, 9, 11 (ready gate, panel verification, timeouts, in-place retry).
   → verify: re-run the 3-job burst 5×; target ≥ 90 % first-attempt success and no 30 s blind
   waits in `params.py`.
3. Items 15–17 (classification, project health, status reset).
   → verify: UI timeouts no longer move accounts to `cooldown`.
4. Items 10, 12, 13, 18 (model confirmation, submit confirmation, stall detection, baseline fix).
   → verify: unit tests for `set_model` label parsing / item waiting; an induced failure
   (e.g. blocked prompt) fails in < 60 s rather than 360 s.
5. Items 14, 19–21 as follow-ups.

# Google Flow Wrapper — Implementation Task Plan

**Source requirement:** [google-flow-wrapper-requirement.md](google-flow-wrapper-requirement.md)
**Version:** 0.1 (MVP)
**Last updated:** 2026-08-14

Status legend: `TODO` · `IN PROGRESS` · `DONE` · `DONE (unverified)` · `BLOCKED` · `DEFERRED`

Tasks are ordered so that each one is independently implementable and testable, and each
depends only on tasks above it.

> ✅ **Update 2026-08-14:** End-to-end image generation now works and was verified against a real
> Google account (see Phase 5 for the full write-up). The remaining gaps are: reference-image
> upload (untested), the model/aspect-ratio option click inside the settings panel (untested),
> and Flow's "confirm before creating" dialog (not encountered, may not apply to this account/tier).

---

## Progress Summary

| Phase | Tasks | Done |
|-------|-------|------|
| 0. Bootstrap | 3 | 3 |
| 1. Config & Models | 4 | 4 |
| 2. Account Storage | 5 | 5 |
| 3. Browser Layer | 6 | 6 |
| 4. Login Flow | 4 | 4 |
| 5. Flow Page Automation | 6 | 6 (✅ verified live end-to-end) |
| 6. Rotation & Concurrency | 4 | 4 |
| 7. Public API | 3 | 3 |
| 8. CLI | 5 | 5 |
| 9. Observability & Resilience | 4 | 2 |
| 10. Hardening & Release | 4 | 1 |
| **Total** | **48** | **43** |

**Test suite:** 82 tests passing · `ruff check` clean · `mypy --strict` clean (see
[Verification](#verification) below for exact commands).

---

## Phase 0 — Project Bootstrap

| # | Task | Requirement | Status |
|---|------|-------------|--------|
| 0.1 | Create `pyproject.toml` (hatchling, py3.11+, deps, `flow` console script, ruff/mypy/pytest config) | NFR-05 | DONE |
| 0.2 | Create `src/google_flow_wrapper/` package skeleton + `tests/`, `.gitignore` (excludes `data/`), `README.md` | NFR-05, NFR-06 | DONE |
| 0.3 | Create `.venv`, install `-e ".[dev]"`, verify `flow version` and `pytest` pass | NFR-05 | DONE |

**Acceptance:** `flow version` prints `0.1.0`; `pytest` green.

---

## Phase 1 — Configuration & Domain Models

| # | Task | Requirement | Status |
|---|------|-------------|--------|
| 1.1 | `models.py`: Pydantic models `Account` (email, label, proxy, status enum, created_at, last_used_at, success_count, fail_count, cooldown_until) and `AccountStatus` enum (`active`, `disabled`, `needs_login`, `cooldown`) | FR-06, FR-09, FR-16 | DONE |
| 1.2 | `models.py`: `GenerationRequest` (prompt, model, aspect_ratio, count, reference_images, timeout) and `GeneratedImage` / `GenerationResult` (bytes, url, local_path, account_email, duration) | FR-01, FR-03 | DONE |
| 1.3 | `config.py`: `Settings` via pydantic-settings — data dir, headless flag, per-account concurrency, default timeouts, retry counts, default output dir; loaded from YAML file + `FLOW_*` env vars | FR-20, NFR-04 | DONE |
| 1.4 | `paths.py`: resolve `data/`, `data/accounts.yaml`, `data/sessions/<email>/`, `data/outputs/`; create dirs on demand with restrictive permissions | NFR-04, §4.6 | DONE |

**Acceptance:** unit tests round-trip models to/from YAML; settings override order env > file > defaults. Verified
by [tests/test_models.py](../../tests/test_models.py), [tests/test_config.py](../../tests/test_config.py),
[tests/test_paths.py](../../tests/test_paths.py).

---

## Phase 2 — Account Storage (`AccountManager`)

| # | Task | Requirement | Status |
|---|------|-------------|--------|
| 2.1 | `accounts/store.py`: load/save `accounts.yaml` atomically (temp file + replace), tolerate missing/corrupt file | FR-11, NFR-04 | DONE |
| 2.2 | `accounts/manager.py`: `add(email, label, proxy)` → creates entry with status `needs_login` + session dir; reject duplicates | FR-07 | DONE |
| 2.3 | `AccountManager.remove(email)` → delete entry and recursively delete its session dir | FR-08 | DONE |
| 2.4 | `AccountManager.list_accounts()`, `enable(email)`, `disable(email)`, `set_status()`, `record_success/record_failure()` metric updates | FR-09, FR-16, FR-23 | DONE |
| 2.5 | `AccountManager.get_available()` → filter out disabled / `needs_login` / in-cooldown accounts | FR-15 | DONE |

**Acceptance:** tests with a temp data dir cover add/remove/enable/disable/duplicate/missing-account cases. Verified
by [tests/test_accounts_store.py](../../tests/test_accounts_store.py),
[tests/test_accounts_manager.py](../../tests/test_accounts_manager.py).

> **Note:** `list()` was renamed to `list_accounts()` — a method literally named `list` broke `mypy --strict`
> (it shadowed the builtin `list` type inside its own return-type annotation).

> **Bug fixed 2026-08-14:** `flow account health` only ever *demoted* an account to `needs_login` on
> failure; a passing check never promoted `needs_login`/`cooldown` back to `active`. Fixed in
> `cli.py::account_health` (skips accounts a user explicitly `disable`d) and covered by a new test
> in [tests/test_cli.py](../../tests/test_cli.py).

---

## Phase 3 — Browser Automation Layer

| # | Task | Requirement | Status |
|---|------|-------------|--------|
| 3.1 | `browser/base.py`: `BrowserBackend` protocol — `browser_context(account, headless) -> AbstractAsyncContextManager[BrowserContext]` | NFR-06 | DONE |
| 3.2 | `browser/camoufox_backend.py`: launch Camoufox per-account, `storage_state` persistence, humanize on | NFR-01, FR-12 | DONE |
| 3.3 | `browser/proxy.py`: validate per-account proxy URL format, bind into Camoufox launch options | NFR-02 | DONE |
| 3.4 | `browser/session.py`: `account_browser(account, paths)` convenience wrapper around `CamoufoxBackend` | FR-11, FR-12 | DONE |
| 3.5 | `browser/humanize.py`: randomized delays, incremental typing, small mouse jitter helpers | NFR-03 | DONE |
| 3.6 | `browser/doctor.py` (`camoufox_status()`) + `flow doctor` CLI check that Camoufox is installed; one-time fetch documented in README | NFR-01 | DONE |

**Acceptance:** launching two accounts concurrently yields isolated contexts; state file written on close. Verified
by [tests/test_browser_camoufox_backend.py](../../tests/test_browser_camoufox_backend.py) (Camoufox itself is
mocked — no real browser is launched in tests), [tests/test_browser_proxy.py](../../tests/test_browser_proxy.py),
[tests/test_browser_doctor.py](../../tests/test_browser_doctor.py).

---

## Phase 4 — Authentication / Login Flow

| # | Task | Requirement | Status |
|---|------|-------------|--------|
| 4.1 | `auth/login.py`: `interactive_login(account, manager, backend)` — open headed browser at Flow, wait for user to finish Google login/2FA | FR-07, §4.6 | DONE |
| 4.2 | Success detection: poll for `AUTHENTICATED_MARKER` with overall timeout; persist storage state (via backend, on context exit) and set status `active` | FR-07, FR-11 | DONE |
| 4.3 | `auth/session_check.py`: `is_logged_in(context)` — headless navigation check returning bool without side effects | FR-10, FR-22 | DONE |
| 4.4 | `relogin(email, manager, backend)` — reuse 4.1 for an existing account | FR-10 | DONE |

**Acceptance:** manual run adds an account, restarting the process reuses the session headlessly. **Verified live
on 2026-08-14** with a real Google account (`flow account add` → headed Camoufox login → `flow account health`
now correctly reports the session as active and promotes the account to `active`).

> **Fixed 2026-08-14:** `AUTHENTICATED_MARKER` (a guessed CSS selector on the public marketing page) never
> worked — that page loads with or without login, so the check was meaningless. Replaced with a URL-based
> check: `is_logged_in`/`interactive_login` now navigate to the real auth-gated app URL (`FLOW_URL`, see
> Phase 5 notes) and check whether Google redirected to `accounts.google.com`. Both
> [tests/test_auth_login.py](../../tests/test_auth_login.py) and
> [tests/test_auth_session_check.py](../../tests/test_auth_session_check.py) were updated to match.

---

## Phase 5 — Flow Page Automation (Generation)

| # | Task | Requirement | Status |
|---|------|-------------|--------|
| 5.1 | `flowpage/selectors.py`: centralize all DOM selectors / roles in one module so UI changes are a single-file fix | NFR-06 | DONE, verified live |
| 5.2 | `flowpage/navigate.py`: open the real app URL, create/open a project (`add_2` button), confirm via the resulting `/project/...` URL | FR-02 | DONE, verified live |
| 5.3 | `flowpage/params.py`: open the "tune" settings panel and pick model/aspect ratio | FR-01 | DONE, panel-open verified; option click still unverified |
| 5.4 | `flowpage/prompt.py`: click-to-focus + type into the real `[role=textbox]` Slate.js prompt box and submit; optional reference-image upload | FR-01, FR-05 | DONE, verified live end-to-end; reference-image upload unverified |
| 5.5 | `flowpage/wait.py`: poll for the real `img[src*='media.getMediaUrlRedirect']` result, with an error-banner fallback classifying quota/auth/timeout errors | FR-02, FR-04 | DONE, verified live; error-banner path still untested (no error was encountered) |
| 5.6 | `flowpage/download.py`: extract, dedupe, and download image URL(s) (resolving relative `src` against the page URL), save with deterministic filenames | FR-02, FR-03 | DONE, verified live |

**Acceptance:** single-account end-to-end run produces at least one saved image from a prompt — **✅ ACHIEVED on
2026-08-14** with the real account `tuanle2x7@gmail.com`. Prompt "a red apple on a wooden table" was submitted,
Flow generated a real image, and it was downloaded and verified as a valid 143 KB PNG matching the prompt.

Key findings from the live run (all now reflected in code):

- The real app lives at `https://labs.google/fx/tools/flow` (not the public marketing page); it redirects to
  `accounts.google.com` when unauthenticated and stays on `labs.google/...` when authenticated. No
  `data-testid`/`aria-label` attributes exist anywhere, and all text is localized (this account renders in
  Vietnamese) — selectors rely on Google's Material Symbols icon-ligature names (`add_2`, `arrow_forward`,
  `tune`), which stay in English regardless of locale.
- The prompt box is a **Slate.js** rich-text editor. Typing character-by-character via `press_sequentially`
  *without first explicitly clicking it* updates the visible DOM text but never establishes Slate's internal
  selection state, leaving the submit button permanently `aria-disabled`. Fix: `prompt.submit_prompt` now does
  an explicit `.click()` to focus before typing.
- `navigate.ensure_project` used to silently swallow any failure to reach a project, which surfaced 30+
  seconds later as an opaque "prompt textbox not found" timeout. It now explicitly waits for the URL to
  contain `/project/` and raises a clear `SelectorNotFoundError` if that never happens.
- The completed image is an `<img>` whose `src` matches `/fx/api/trpc/media.getMediaUrlRedirect?name=<uuid>` —
  a stable backend path (its CSS classes are shared with the unrelated user-avatar image, so those alone
  aren't usable). Each generated image appears **twice** in the DOM (main canvas + agent chat log) with the
  same `src` — `download.collect_image_urls` dedupes by URL before slicing to the requested `count`.
- The `src` is a **relative URL** — `download.download_images` now resolves it against `page.url` via
  `urllib.parse.urljoin` before fetching.
- There is **no separate "image mode" tab** — Flow's default UI is already an agent-style prompt box, so
  `navigate.switch_to_image_mode()` is a documented no-op kept only for interface stability.
- Flow's "confirm before creating" setting (observed in the settings panel, defaulting to *always confirm*)
  did **not** show a confirmation dialog during the real run — it may only apply to video, or a different
  account tier. Not handled in code; revisit if a future run gets stuck waiting past submit.

[tests/test_flowpage_wait.py](../../tests/test_flowpage_wait.py) and
[tests/test_flowpage_download.py](../../tests/test_flowpage_download.py) cover error-classification, URL
dedup, and relative-URL resolution against mocked Playwright `Page`/`Locator` objects.

---

## Phase 6 — Rotation, Concurrency & Retries

| # | Task | Requirement | Status |
|---|------|-------------|--------|
| 6.1 | `rotation/strategy.py`: `RoundRobinStrategy` (MVP) behind a `RotationStrategy` protocol; `LeastLoadedStrategy` stub | FR-13 | DONE |
| 6.2 | `rotation/limiter.py`: per-account `asyncio.Semaphore` (configurable, default 1) + global concurrency cap | FR-14, NFR-07 | DONE |
| 6.3 | `rotation/scheduler.py`: acquire next available account, run job, release, apply cooldown on failure | FR-13, FR-15 | DONE |
| 6.4 | Retry policy: up to `max_retries` attempts, each on a different account; on any failure, record `fail_count` + cooldown and retry | FR-04, FR-23 | DONE (simplified — no backoff, no auth-specific handling yet; see Phase 9.4) |

**Acceptance:** unit tests with a fake job runner prove even distribution across accounts and that concurrency
limits hold. Verified by [tests/test_rotation_strategy.py](../../tests/test_rotation_strategy.py),
[tests/test_rotation_limiter.py](../../tests/test_rotation_limiter.py),
[tests/test_rotation_scheduler.py](../../tests/test_rotation_scheduler.py).

---

## Phase 7 — Public Library API (`FlowClient`)

| # | Task | Requirement | Status |
|---|------|-------------|--------|
| 7.1 | `client.py`: `FlowClient(settings)` with `async generate_image(prompt, **opts)` wiring scheduler + page automation | FR-17 | DONE |
| 7.2 | `async generate_batch(prompts, **opts)` — parallel dispatch honouring rotation and limits (`asyncio.gather`) | FR-13, FR-17 | DONE |
| 7.3 | Sync facade `generate_image_sync(...)` wrapping `asyncio.run` | FR-19 | DONE |

**Acceptance:** `from google_flow_wrapper import FlowClient` works; both async and sync paths covered by tests using
a mocked `_run_generation`. Verified by [tests/test_client.py](../../tests/test_client.py).

---

## Phase 8 — CLI

| # | Task | Requirement | Status |
|---|------|-------------|--------|
| 8.1 | `flow generate "<prompt>" [--model --aspect --count --out --timeout]` (no `--account` override yet — rotation always picks) | FR-18 | DONE |
| 8.2 | `flow account add|remove|list|enable|disable|relogin` | FR-07, FR-08, FR-09, FR-10, FR-18 | DONE |
| 8.3 | `flow account health` — per-account login check, marks `needs_login` on failure | FR-22 | DONE |
| 8.4 | `flow config show|path` + `--config` / `--data-dir` global options | FR-20 | DONE |
| 8.5 | `flow doctor` — verify Camoufox binary is installed and print the data dir | NFR-01, §4.6 | DONE (simplified — no explicit Python-version/config-validity checks yet) |

**Acceptance:** every command has `--help`; CLI tests via `typer.testing.CliRunner` with mocked dependencies
(`FlowClient`, `CamoufoxBackend`, `is_logged_in`, `relogin_account`, `camoufox_status`) so no real browser is
launched. Verified by [tests/test_cli.py](../../tests/test_cli.py).

---

## Phase 9 — Observability & Resilience

| # | Task | Requirement | Status |
|---|------|-------------|--------|
| 9.1 | `logging_setup.py`: `configure_logging()` / `get_logger()` — structlog config, JSON or console renderer | FR-21 | DONE |
| 9.2 | Wire `get_logger()` into `scheduler.py` / `client.py` / `login.py` to log every major action (account selected, navigation, submit, complete, download, error) with account + job id; never log cookies/credentials | FR-21, §4.6 | TODO |
| 9.3 | `errors.py`: exception hierarchy (`FlowError`, `AuthError`, `GenerationTimeoutError`, `QuotaExceededError`, `NoAvailableAccountError`, `SelectorNotFoundError`, `AccountAlreadyExistsError`, `AccountNotFoundError`) | FR-04, NFR-06 | DONE |
| 9.4 | Auto-status transitions: currently *every* job failure sets a flat cooldown via `AccountManager.set_cooldown`; still TODO is distinguishing `AuthError` (→ `needs_login`) from `QuotaExceededError`/generic failures (→ cooldown) inside `JobScheduler`. **Observed live:** a `GenerationTimeoutError` from a stale/wrong selector was indistinguishable from a real account problem — both just triggered a cooldown, requiring a manual `flow account enable` to recover | FR-23, FR-15 | TODO |

**Acceptance:** a forced failure produces a structured log record and the correct account status change — the
logging utility exists and is tested ([tests/test_logging_setup.py](../../tests/test_logging_setup.py)), but it is
not yet called from the business-logic modules (9.2), and status transitions aren't yet error-type-aware (9.4).

---

## Phase 10 — Hardening & Release

| # | Task | Requirement | Status |
|---|------|-------------|--------|
| 10.1 | Secure data dir: `paths.py` chmods to owner-only on POSIX; **no equivalent restriction is applied on Windows (NTFS ACLs)**; no at-rest encryption for `storage_state.json` yet | §4.6, NFR-04 | IN PROGRESS |
| 10.2 | Test suite: 82 unit tests covering models/config/paths/accounts/browser(mocked)/auth(mocked)/rotation/client(mocked)/CLI(mocked); **no automated integration tests against the live site** (no `--runlive` marker yet), though the full pipeline was manually verified live on 2026-08-14 | — | IN PROGRESS |
| 10.3 | Lint & type gate: `ruff check` and `mypy --strict` both clean (see Verification below); no pre-commit hook configured yet | NFR-06 | DONE |
| 10.4 | Usage docs: README quickstart exists; still missing a config reference, ToS/risk disclaimer, and a verified MVP success-criteria checklist | §4.6, §6 | TODO |

---

## Verification

Commands used to validate this implementation (run from the repo root):

```powershell
.\.venv\Scripts\python.exe -m pytest -q             # 79 passed
.\.venv\Scripts\python.exe -m ruff check src tests  # All checks passed!
.\.venv\Scripts\python.exe -m mypy                  # Success: no issues found in 32 source files
```

All three commands were green as of 2026-08-14. No test launches a real browser or hits the live
`labs.google/flow` site — Camoufox, Playwright pages/locators, and `FlowClient._run_generation`
are all mocked/monkeypatched in tests, since the real DOM selectors are unverified (see the
warning at the top of this document).

---

## Suggested Milestones

| Milestone | Phases | Outcome | Status |
|-----------|--------|---------|--------|
| **M1 — Skeleton** | 0–2 | Accounts can be added/removed/listed; nothing browses yet. | DONE |
| **M2 — Logged-in session** | 3–4 | Interactive login works; sessions persist and are reusable headlessly. | DONE — verified live with a real account on 2026-08-14 |
| **M3 — First image** | 5 | Single-account end-to-end generation returns a saved image. | ✅ DONE — verified live on 2026-08-14 (real image generated and downloaded) |
| **M4 — Multi-account MVP** | 6–8 | Rotation, `FlowClient`, and full CLI operational. | DONE (code + unit tests; real end-to-end run blocked by M3) |
| **M5 — Production-ready MVP** | 9–10 | Logging, resilience, security, docs, and tests complete. | IN PROGRESS (9.2/9.4/10.1/10.2/10.4 remaining) |

**Recommended next steps, in order:**
1. Capture real Flow selectors from a live logged-in session and update `flowpage/selectors.py` (unblocks M3).
2. Run one real end-to-end `flow account add` → `flow generate` cycle against an actual account.
3. Wire structured logging into `scheduler.py` / `client.py` / `login.py` (9.2).
4. Make `JobScheduler` react differently to `AuthError` vs. `QuotaExceededError` vs. generic failures (9.4).
5. Add integration tests behind a `--runlive` marker and flesh out README docs (10.2, 10.4).

---

## Deferred (Post-MVP)

- Video generation (Veo)
- Credit/quota scraping and quota-aware account selection
- Distributed workers (Redis/RabbitMQ)
- Web dashboard
- CAPTCHA solving integration
- Official API fallback

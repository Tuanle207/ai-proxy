# Perplexity Provider Integration Plan

**Refines:** [multi-provider-refactor-plan.md](./multi-provider-refactor-plan.md) §Phase 9
**Parent phase status:** 6 of 8 tasks done (unverified until live recon); 2 blocked on live access
**Version:** 0.3 (full implementation, selectors unverified)
**Last updated:** 2026-08-16

Status legend: `TODO` · `IN PROGRESS` · `DONE` · `DONE (unverified)` · `BLOCKED` · `DEFERRED`

---

## 1. Context

Phases 1–8 of the refactor are **DONE** (62/72 master tasks). The provider seam is built,
tested with a `FakeProvider`, and proven end-to-end by the `google_flow` provider. Perplexity is
the *first real second provider*: its only job is to prove the seam supports a second modality
(`TEXT`) and a second site, with zero provider conditionals in `core/`.

What already exists and is reusable **unchanged**:

| Piece | Location |
|-------|----------|
| Provider seam (spec, adapter, auth, session, params, registry) | `src/ai_proxy/core/provider/` |
| Per-provider account registry + session storage | `src/ai_proxy/core/accounts/`, `core/paths.py` |
| `TEXT` artifact handling (inline text, byte count, `/v1/artifacts/{id}`) | `core/worker/metadata.py`, `core/service/routers/artifacts.py` |
| Per-provider slot pools + browser backend | `core/rotation/pool.py`, `core/browser/` |
| `TaskRequest`/`TaskResult`/`Artifact` domain models | `core/models.py` |
| Authoring guide (copy-paste skeleton) | [provider-authoring-guide.md](./provider-authoring-guide.md) |

The reference implementation to mirror is `google_flow`:

| File | Reference | Perplexity equivalent |
|------|-----------|-----------------------|
| `params.py` (29 L) | `GoogleFlowParams(ProviderParams)` | `PerplexityParams` |
| `config.py` (18 L) | `GoogleFlowSettings(ProviderSettings)` | `PerplexitySettings` |
| `auth.py` (115 L) | `GoogleFlowAuth` + `interactive_login` | `PerplexityAuth` |
| `adapter.py` (140 L) | `GoogleFlowAdapter` | `PerplexityAdapter` |
| `page/` (7 files) | `selectors`/`navigate`/`prompt`/`wait`/`download`/`params` | `selectors`/`navigate`/`prompt`/`wait`/`extract` |
| `__init__.py` (40 L) | `register(ProviderSpec(...))` | same |

---

## 2. Scope & Target

**Capabilities (frozen in master plan §2.4.1 / task 9.6):**

| Field | Value | Note |
|-------|-------|------|
| `task_kinds` | `frozenset({TaskKind.TEXT})` | First cut is text-only |
| `max_outputs_per_request` | `1` | One answer per request |
| `supports_reference_inputs` | `False` | (may be revisited later for file-upload) |
| `supports_workspace_reuse` | `True` | Perplexity *threads* |
| `requires_browser` | `True` | Browser-automated, like Flow |

**Perplexity params** (`PerplexityParams`, master task 9.2): `focus`, `model`, `search_mode`,
`include_citations`.

**Target layout:**

```
src/ai_proxy/providers/perplexity/
├── __init__.py            # build + register() ProviderSpec
├── params.py              # PerplexityParams
├── config.py              # PerplexitySettings (AI_PROXY_PERPLEXITY_*)
├── auth.py                # PerplexityAuth (AuthHandler)
├── adapter.py             # PerplexityAdapter (ProviderAdapter)
├── errors.py              # site banner/error → core error mapping (optional; see W4)
├── api.py                 # APIRouter → /v1/providers/perplexity
├── cli.py                 # typer.Typer → aip perplexity
└── page/
    ├── __init__.py
    ├── selectors.py       # one comment per selector: "why stable"
    ├── navigate.py        # open app, new/resume thread
    ├── prompt.py          # submit prompt
    ├── wait.py            # answer-complete detection
    └── extract.py         # answer markdown + citations
```

---

## 3. Blockers & Preconditions

Two master tasks are `BLOCKED` because they need **live Perplexity access with a human**:

| Task | Blocker | What unblocks it |
|------|---------|------------------|
| 9.1 Reconnaissance | Needs a headed Camoufox session + a logged-in Perplexity account | Human provides an account + ~30 min of guided headed-browser recon |
| 9.8 Live verification | Needs a registered account on the dev machine | Account logged in via `aip accounts --provider perplexity login` |

Everything else (scaffolding, params, config, registration, adapter skeleton, api/cli, tests) can
proceed **without** live access and is structured so the selector-dependent work lands after 9.1.

---

## 4. Task Plan

Ordered so each task is independently implementable and testable, and depends only on tasks above
it. Workstreams are grouped by dependency: **W1–W2** (no live access needed) → **W3–W5** (needs 9.1)
→ **W6–W8** (finishing + live proof).

### W1 — Scaffolding & parameters (master 9.2)

| # | Task | Rationale | Status |
|---|------|-----------|--------|
| P1.1 | Create `providers/perplexity/` package with empty `__init__.py`, `page/__init__.py`, `errors.py` | Match the `google_flow` layout so later tasks have a home | DONE |
| P1.2 | `providers/perplexity/config.py`: `PerplexitySettings(ProviderSettings)` with `env_prefix="AI_PROXY_PERPLEXITY_"`, `extra="ignore"`. Fields: `base_url: str = "https://www.perplexity.ai"`, `login_timeout: float = 300.0`, `delete_thread_after_job: bool = False` | Mirror `GoogleFlowSettings` (18 L); keeps site facts out of core | DONE |
| P1.3 | `providers/perplexity/params.py`: `PerplexityParams(ProviderParams)` with `focus: Literal["auto","web","academic","writing","math","video","social","reasoning"] \| None = None`, `model: str \| None = None`, `search_mode: str \| None = None`, `include_citations: bool = True`; `extra="forbid"` inherited from `ProviderParams` | Powers `/v1/providers/perplexity` JSON Schema + CLI `-p` validation. `focus`/`model`/`search_mode` keep `None` defaults = "use site default" (safe until recon confirms the real control names) | DONE |
| P1.4 | Unit test: `PerplexityParams` round-trips through `json_schema()`, rejects an unknown param (e.g. `aspect_ratio`) with a `ValidationError` | Proves `extra="forbid"` + the `params_model` export contract | DONE |

**Verify:** `pytest tests/test_perplexity_params.py -q` green; `json_schema(PerplexityParams)` includes
`focus`, `model`, `search_mode`, `include_citations`.

### W2 — Provider registration & discovery (master 9.6, structural half)

| # | Task | Rationale | Status |
|---|------|-----------|--------|
| P2.1 | `providers/perplexity/__init__.py`: build + `register(ProviderSpec(name="perplexity", display_name="Perplexity", capabilities=Capabilities(task_kinds=frozenset({TaskKind.TEXT}), max_outputs_per_request=1, supports_reference_inputs=False, supports_workspace_reuse=True, requires_browser=True), params_model=PerplexityParams, settings_model=PerplexitySettings, build_adapter=PerplexityAdapter, build_auth=PerplexityAuth, api_router=router, cli_app=perplexity_app))` | Declarative registration, copied from `google_flow/__init__.py` | DONE |
| P2.2 | Add `import ai_proxy.providers.perplexity  # noqa: F401` to `providers/__init__.py` | Built-ins self-register on import | DONE |
| P2.3 | Unit test: `registry.names()` includes `"perplexity"` and `get("perplexity").capabilities.task_kinds == {TaskKind.TEXT}` (a sibling test to `test_provider_seam.py`) | Proves registration + discovery before any page logic exists | DONE |

**Note:** P2.1 imports `PerplexityAdapter`, `PerplexityAuth`, `router`, `perplexity_app` — those
modules must exist (even as stubs) before P2.1 lands. Create minimal stub classes for the adapter
and auth in W1 (or merge P2 into a single "scaffold + register" task if stubs are cleaner). The
ordering constraint is: **registration lands only after adapter/auth stubs exist.**

**Verify:** `pytest tests/test_provider_seam.py -q` green; `aip providers show perplexity` renders
capabilities.

### W3 — Reconnaissance (master 9.1) — *BLOCKED on live access*

| # | Task | Rationale | Status |
|---|------|-----------|--------|
| P3.1 | With a headed Camoufox session, record: (a) login entry + logged-in probe, (b) prompt box selector, (c) submit control/keystroke, (d) streaming-answer completion signal, (e) citation list DOM, (f) thread URL shape (`/threads/<id>` vs `/search/<slug>`), (g) error/rate-limit/login banners | Every selector in P4/P5 derives from this | IN PROGRESS |
| P3.2 | Write findings into `page/selectors.py` with the `google_flow` convention: **one comment per selector explaining *why* it is stable** (prefer backend-path substrings, `role`/`aria` attributes, or stable text over per-build CSS class hashes); mark inferred-but-unverified selectors explicitly | Selector churn is the #1 maintenance cost (see authoring guide §"Selector discipline") | IN PROGRESS |
| P3.3 | Record screenshots/DOM samples of the logged-in answer view + login redirect into `docs/multi-provider-refactor/perplexity-recon/` (or a dated note in this doc) | A stable reference for future selector regression debugging | BLOCKED |

**Output of W3 = the input to W4–W5.** Do not write `navigate.py`/`prompt.py`/`wait.py`/
`extract.py` against guessed selectors.

### W4 — Site-driving page helpers (master 9.4) — *depends on W3*

| # | Task | Rationale | Status |
|---|------|-----------|--------|
| P4.1 | `page/navigate.py`: `open_perplexity(page)`, `ensure_thread(page, reuse: bool) -> WorkspaceRef | None`, `new_thread(page) -> WorkspaceRef` (mirror `google_flow/page/navigate.py`) | Open / new-thread / resume-thread, the thread = workspace | DONE (unverified) |
| P4.2 | `page/prompt.py`: `submit_prompt(page, text)` (mirror `google_flow/page/prompt.py` incl. humanized typing) | Submit the query | DONE (unverified) |
| P4.3 | `page/wait.py`: `wait_for_answer(page, timeout)` — detect **completion**, not merely "text appeared" (e.g. stop the streaming caret, watch for the sources block / stop button disappearance), not a fixed sleep | The #1 source of flaky `TEXT` jobs; mirrors Flow's `wait_for_completion` | DONE (unverified) |
| P4.4 | `page/extract.py`: `extract_answer(page) -> tuple[str, list[dict]]` returning answer markdown + citations (title/url), plus `extract_thread_ref(page) -> WorkspaceRef | None` | Produces the `Artifact(kind=TEXT)` payload | DONE (unverified) |

**Verify:** a small headed smoke (once an account exists) driving `open → prompt → wait → extract`
and printing the answer; unit-testable pieces (URL parsing, markdown cleanup) covered with `pytest`
using saved DOM fixtures.

### W5 — Auth (master 9.3) — *partially depends on W3*

| # | Task | Rationale | Status |
|---|------|-----------|--------|
| P5.1 | `providers/perplexity/auth.py`: `PerplexityAuth(AuthHandler)` implementing `login_url`, `is_logged_in(session)`, `interactive_login(session)`, `probe_session(session)` | Mirrors `GoogleFlowAuth` (115 L) using the login probe recorded in P3.1 | DONE (unverified) |
| P5.2 | Reuse `core/browser` session persistence under `data/providers/perplexity/sessions/<email>/storage_state.json` (no code needed — verify via `aip accounts --provider perplexity login`) | Blocker 1.2.2 already solved by `core/paths.py` provider-scoping | DONE (unverified) |

**Verify:** `aip accounts --provider perplexity login` completes an interactive login and
`aip accounts --provider perplexity health` reports `is_logged_in` correctly (live).

### W6 — Adapter (master 9.5) — *depends on W4, W5*

| # | Task | Rationale | Status |
|---|------|-----------|--------|
| P6.1 | `providers/perplexity/adapter.py`: `PerplexityAdapter(ProviderAdapter)`. `execute(session, request)`: validate `PerplexityParams`, `navigate.ensure_thread`, `session.on_workspace_created(ref)` on new threads, `prompt.submit_prompt`, `wait.wait_for_answer`, `extract.extract_answer`, then return `TaskResult(artifacts=[Artifact(kind=TEXT, mime="text/markdown", text=answer, meta={"citations": [...]})], workspace_ref=thread_ref)` | Mirrors `GoogleFlowAdapter` (140 L); proves the `TEXT` path | DONE (unverified) |
| P6.2 | `classify_failure(exc)`: map Perplexity rate-limit/login banners (from P3.1g) to `FailurePolicy`; delegate to `default_classify_failure` otherwise | Provider-specific errors, shared defaults | DONE (unverified) |
| P6.3 | `health_check(session)`: navigate + logged-in probe (same as Flow's `health_check`) | `/readyz` + `aip doctor` readiness | DONE (unverified) |
| P6.4 | `cleanup(session, ref)`: delete thread when `delete_thread_after_job` (best-effort, never fail a successful job) | Mirrors Flow's `cleanup` | DONE (unverified) |
| P6.5 | Unit tests with `FakeProvider`-style fixtures + a fake `ProviderSession.page` (Playwright async mock or recorded DOM): assert `execute` returns one `TEXT` artifact with `text` and `meta["citations"]`, and that `classify_failure` handles an unknown exception by returning `None` | Adapter logic tested without a browser | DONE |

**Verify:** `pytest tests/test_perplexity_adapter.py -q` green; `mypy --strict src` clean.

### W7 — Provider-owned API + CLI (master 9.7)

| # | Task | Rationale | Status |
|---|------|-----------|--------|
| P7.1 | `providers/perplexity/api.py`: `router = APIRouter()` with `GET /threads` (list workspace refs from `provider_state`/DB) and optionally `DELETE /threads/{id}`; mounted at `/v1/providers/perplexity` by core | Mirrors `google_flow/api.py` (`/projects/orphans`, `/projects/prune`) | DONE |
| P7.2 | `providers/perplexity/cli.py`: `perplexity_app = typer.Typer()` with `threads list|delete`; mounted as `aip perplexity` | Mirrors `google_flow/cli.py` | DONE |
| P7.3 | Wire `api_router=router`, `cli_app=perplexity_app` into the `ProviderSpec` (P2.1) | Provider-owned api/cli surfaces | DONE |

**Verify:** `GET /v1/providers/perplexity/threads` returns 200; `aip perplexity threads list` runs.

### W8 — Live verification (master 9.8) — *BLOCKED on live access*

| # | Task | Rationale | Status |
|---|------|-----------|--------|
| P8.1 | `aip accounts --provider perplexity login` with a real account; then `aip run --provider perplexity --kind text "summarize the 2026 EU AI Act timeline"` | End-to-end `TEXT` proof | BLOCKED |
| P8.2 | Same via `POST /v1/tasks`; confirm SSE events, `Artifact` persistence, `/v1/artifacts/{id}` inline text | API surface proof | BLOCKED |
| P8.3 | Run a Flow job and a Perplexity job **concurrently**; confirm independent pools, cooldowns, and recovery (no cross-provider interference) | The multi-provider guarantee | BLOCKED |
| P8.4 | `pytest`, `ruff check src tests`, `mypy --strict src`, `lint-imports` all green | Project verification standard | BLOCKED |

### Implementation notes (2026-08-16)

- **Recon round 1 (done):** confirmed against a live session that the composer is a contenteditable
  `<div id="ask-input">` (not a textarea), submit is `button[aria-label="Submit"]`, the model picker
  is `button[aria-label="Model"]` → `[role="menuitemradio"]`, and thread URLs are `/search/<uuid>`.
  `selectors.py` + `prompt.py` + `extract.py` updated accordingly.
- **Still unverified** (`ANSWER_BODY`, `STOP_BUTTON`, `CITATION_LINK`, `LOGIN_BUTTON`): needs a
  follow-up capture — submit a query, click the answer body / a citation, and record the streaming
  "stop" control + the logged-out landing.
- **W1, W2, W7 are DONE and verified** (`pytest` 29 passed, `ruff check src tests scripts` clean,
  `mypy --strict src` clean). The package is registered and discoverable; `aip providers show
  perplexity` renders capabilities + params schema; `aip perplexity threads list` mounts.
- **W4, W5, W6 are DONE (unverified):** `page/selectors.py`, `page/navigate.py`, `page/prompt.py`,
  `page/wait.py`, `page/extract.py`, `auth.py`, and `adapter.py` are fully implemented behind the
  seam; the remaining unverified selectors above must be confirmed before P8.x live verification.
- **P1.3 deviation:** `focus`/`model`/`search_mode` are typed `str | None` (not the `Literal[...]`
  in the task text). They are validated but **not applied** by the adapter yet; `include_citations`
  is honored.
- **Auth-routing gap fixed:** `cli/accounts_cmd.py` now routes login/health through
  `spec.build_auth` (the registry `AuthHandler`), so `aip accounts --provider perplexity
  login|health` works once the probe is confirmed.
- **New tool:** `scripts/recon_perplexity.py` — logs in a live session (persists storage state) and
  (`--inspect`) dumps a DOM report + interactive click-capture (now incl. an `html` snippet) for
  selector discovery.
- **Pre-existing test noise:** the full `pytest` run may emit an unretrieved
  `ProgrammingError('Cannot operate on a closed database.')` from a `WorkerEngine._run_job` task
  racing test teardown in `test_worker_multiprovider.py` — unrelated to this work.

---

## 5. Acceptance Criteria

1. `registry.names()` reports both `google_flow` and `perplexity`; `GET /v1/providers` lists both
   with correct capabilities.
2. `aip run --provider perplexity --kind text "…"` returns one `TEXT` artifact (answer + citations)
   end-to-end against a live account.
3. `POST /v1/tasks {provider:"perplexity", kind:"text", params:{include_citations:false}}` validates
   params (bad param → 422 naming the field) and flows through SSE → artifact persistence →
   `/v1/artifacts/{id}` inline text.
4. Flow + Perplexity jobs run **concurrently** with independent pools; a Perplexity failure never
   touches a Flow account.
5. **Zero provider conditionals in `core/`** — enforced by `lint-imports` (the Phase 0.2/10.3
   contract) and confirmed by `grep -r "perplexity" src/ai_proxy/core/` returning nothing.
6. `pytest` · `ruff check src tests` · `mypy --strict src` all green.

---

## 6. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Perplexity anti-bot blocks Camoufox automation | Medium | Medium | Recon-first (P3.1): if automation is not viable, the same `ProviderSpec` supports `requires_browser=False` + `ProviderSession.http`; the seam survives either way (master §4) |
| Streaming-answer "completion" detection is flaky | Medium | Medium | P4.3 detects an explicit completion signal (stop button / sources block), never a fixed sleep; P4.4 + fixtures make it unit-testable |
| `focus`/`model` enum names differ from the real UI | Medium | Low | P1.3 keeps them `None`-defaulted and unvalidated until recon (P3.1) confirms the real control names; they are additive, not breaking |
| Recon findings go stale (site churn) | High | Low | P3.2/P3.3 record *why* each selector is stable + DOM samples; selectors live in one file for cheap updates |
| Scope creep into full Perplexity API parity | High | Medium | Non-goals (§7) are explicit; first cut is `TEXT` only |

---

## 7. Non-Goals (this integration)

- No Perplexity **API-key** integration — browser sessions only (master §5).
- No file/image uploads or `FILE`/`IMAGE` kinds on Perplexity (`supports_reference_inputs=False`).
- No cross-provider routing/fallback; the caller picks `provider`.
- No prompt templating / agent chaining.
- No persistence of Perplexity threads beyond the opaque `workspace_ref` + `provider_state` JSON.

---

## 8. Verification Commands

```powershell
# from repo root, with .venv active
ruff check src tests
mypy --strict src
pytest -q

# architecture guard (no core → provider imports, no sibling imports)
lint-imports

# discovery + params schema
aip providers list
aip providers show perplexity

# live smoke (after W8 unblocked)
aip doctor
aip run --provider perplexity --kind text "summarize the 2026 EU AI Act timeline"
aip run --provider google_flow "a red apple on a wooden table" --count 1   # regression

# service
aip serve --port 8080
python scripts/e2e_service_test.py
```

---

## 9. Dependency Summary (task → unblocks)

| Do first | Needed before | Blocked on |
|----------|--------------|------------|
| P1.1–P1.4 (scaffold, params, config) | P2.1 (register spec) | — |
| P2.1–P2.3 (stub adapter/auth + register) | W6 (real adapter), W5 (real auth) | — |
| P3.1–P3.3 (recon) | P4.x (page), P5.x (auth probe), P6.2 (failure map) | **live account + human** |
| P4.1–P4.4 (page) | P6.1 (adapter execute) | P3 |
| P5.1–P5.2 (auth) | P8.1 (login) | P3 |
| P6.1–P6.5 (adapter) | P7.3 (wire api/cli), P8.x (live) | P4, P5 |
| P8.1–P8.4 (live verify) | acceptance | **live account** |

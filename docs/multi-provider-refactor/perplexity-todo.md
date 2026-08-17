# Perplexity Integration — TODO

Status: implementation complete except selector confirmation + live verification.

## Blocked on live recon (user capture)

- [x] Capture `ANSWER_BODY` — `div[data-renderer='lm']` (markdown-renderer marker, more stable
  than the churny Tailwind `prose` classes)
- [x] Capture `STOP_BUTTON` — `button[aria-label='Stop response (Esc)']`
- [x] Confirm `LOGIN_BUTTON` — logged-out sidebar shows a "Sign In" `<div>` (text-matched, not
  an anchor/button): `text=Sign In`

Capture with:

```
.venv\Scripts\python scripts\recon_perplexity.py --email <you@example.com> --inspect
```

## After selectors are confirmed

- [x] Update `src/ai_proxy/providers/perplexity/page/selectors.py` (replace UNVERIFIED constants)
- [x] Remove the "UNVERIFIED" markers from `selectors.py` docstring
- [x] Citation extraction dropped entirely (not needed): removed `CITATION_LINK`,
  `include_citations`, and `extract_answer`'s citations return value

## Live verification (P8)

- [ ] `aip accounts --provider perplexity login <email>` (verify the logged-in probe)
- [ ] `aip run --provider perplexity --kind text "summarize the 2026 EU AI Act timeline"`
- [ ] `POST /v1/tasks {provider:"perplexity", kind:"text", ...}` → SSE → `/v1/artifacts/{id}` inline text
- [ ] Run a Flow job + a Perplexity job concurrently; confirm independent pools

## Always

- [x] `pytest -q` · `ruff check src tests scripts` · `mypy --strict src` green
  (pinned `numpy<2.3` in `pyproject.toml`: newer numpy stubs use PEP 695 `type` aliases
  that mypy can't parse under this project's `python_version = "3.11"` setting)

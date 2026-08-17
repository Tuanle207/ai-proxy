# Perplexity Integration — TODO

Status: implementation complete except selector confirmation + live verification.

## Blocked on live recon (user capture)

- [ ] Capture `ANSWER_BODY` — container holding the assistant's answer markdown
- [ ] Capture `STOP_BUTTON` — the square "stop" control while streaming
- [ ] Capture `CITATION_LINK` — a source link in the answer's Sources list
- [ ] Confirm `LOGIN_BUTTON` — logged-out "Log in"/"Sign up" control (text + tag)

Capture with:

```
.venv\Scripts\python scripts\recon_perplexity.py --email <you@example.com> --inspect
```

Then: submit a query, click the stop button while streaming (suppressed by the listener),
click the answer text, click a citation link, and paste the output (includes `html` snippet).

## After selectors are confirmed

- [ ] Update `src/ai_proxy/providers/perplexity/page/selectors.py` (replace UNVERIFIED constants)
- [ ] Remove the "UNVERIFIED" markers from `selectors.py` docstring

## Live verification (P8)

- [ ] `aip accounts --provider perplexity login <email>` (verify the logged-in probe)
- [ ] `aip run --provider perplexity --kind text "summarize the 2026 EU AI Act timeline"`
- [ ] `POST /v1/tasks {provider:"perplexity", kind:"text", ...}` → SSE → `/v1/artifacts/{id}` inline text
- [ ] Run a Flow job + a Perplexity job concurrently; confirm independent pools

## Always

- [ ] `pytest -q` · `ruff check src tests scripts` · `mypy --strict src` green

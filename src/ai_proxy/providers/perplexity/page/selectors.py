"""DOM selectors and constants for the Perplexity web app.

Verified 2026-08-16 against a live, logged-in session (via `scripts/recon_perplexity.py`):

- The composer is a contenteditable `<div>`, **not** a `<textarea>`: `id="ask-input"` with
  `role="textbox"`. The `id` is a stable semantic anchor, unlike the per-build Tailwind utility
  classes in `cls` (which churn and must never be used).
- The submit control is `button[aria-label="Submit"]`.
- Thread URLs are `/search/<uuid>` (not a slug); saved sessions live under `/library`.
- The model picker is `button[aria-label="Model"]`; its options are `[role="menuitemradio"]`.

Still **UNVERIFIED** (recon follow-up required): the logged-out probe (`LOGIN_BUTTON`), the
streaming "stop" control (`STOP_BUTTON`), the answer body (`ANSWER_BODY`), and the citation list
(`CITATION_LINK`).
"""

from __future__ import annotations

# Canonical app entry point. Stable.
PERPLEXITY_URL = "https://www.perplexity.ai"

# --- Verified against a live session (2026-08-16) ---

# The composer: a contenteditable <div> with a stable `id`. `role="textbox"` also matches, but
# the id is more specific and there is exactly one ask-input on the page.
PROMPT_TEXTBOX = "#ask-input"

# Submit: stable aria-label. Clicked after typing (it only becomes enabled once text is present).
SUBMIT_BUTTON = "button[aria-label='Submit']"

# Model picker trigger + its options (options are `role="menuitemradio"` with the model name as
# text, e.g. "GPT-5.6 Terra", "Claude Sonnet 5").
MODEL_BUTTON = "button[aria-label='Model']"
MODEL_OPTION = "[role='menuitemradio']"

# New answers land on /search/<uuid>; saved sessions are under /library.
SEARCH_URL_MARKER = "/search/"

# --- UNVERIFIED (recon follow-up required) ---

# Logged-out probe: hypothesis — the logged-out landing exposes a "Log in"/"Sign up" control that
# disappears once authenticated (the logged-in header instead shows the account button).
LOGIN_BUTTON = "a:has-text('Log in')"

# Streaming indicator: hypothesis — a square "stop" control is visible while the answer streams
# and is removed on completion. Confirm the actual aria-label/text.
STOP_BUTTON = "button[aria-label*='Stop']"

# The assistant's answer body. Hypothesis: answers render as markdown in a "prose" container;
# `.last` picks the most recent assistant message over earlier ones in the thread.
ANSWER_BODY = "div[class*='prose']"

# Citation sources: links inside the answer's "Sources" list.
CITATION_LINK = "a[href^='http']"

"""DOM selectors and constants for the Perplexity web app.

Verified 2026-08-16/17 against a live, logged-in session (via `scripts/recon_perplexity.py`):

- The composer is a contenteditable `<div>`, **not** a `<textarea>`: `id="ask-input"` with
  `role="textbox"`. The `id` is a stable semantic anchor, unlike the per-build Tailwind utility
  classes in `cls` (which churn and must never be used).
- The submit control is `button[aria-label="Submit"]`.
- Thread URLs are `/search/<uuid>` (not a slug); saved sessions live under `/library`.
- The model picker is `button[aria-label="Model"]`; its options are `[role="menuitemradio"]`.
- The streaming stop control is `button[aria-label="Stop response (Esc)"]`.
- The answer body renders as `div[data-renderer="lm"]` (a markdown-renderer marker attribute,
  more stable than its churny Tailwind `prose` classes).
- The logged-out sidebar exposes a "Sign In" control (a plain `<div>` with that exact text, not
  an anchor/button — matched by Playwright's text engine).
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

# Logged-out probe: the sidebar's bottom item reads "Sign In" (a plain <div>, not an anchor), so
# match by text rather than tag/attribute. Used by `wait_for_answer` to detect a login wall
# mid-run; the logged-in probe itself uses the positive bell marker below.
LOGIN_BUTTON = "text=Sign In"

# Logged-in marker: the notification bell (`#pplx-icon-bell`) only renders for authenticated
# users. Its `<use>` references the icon via `xlink:href`, a *namespaced* attribute — plain
# `[href=...]` and escaped `[xlink\:href=...]` do NOT match it (verified live); the any-namespace
# attribute selector `[*|href=...]` does (verified against Camoufox 2026-08-17).
LOGGED_IN_BELL = "use[*|href='#pplx-icon-bell']"

# The streaming "stop" control (square icon button), confirmed via recon.
STOP_BUTTON = "button[aria-label='Stop response (Esc)']"

# The assistant's answer body: `data-renderer="lm"` marks markdown-rendered content; `.last`
# picks the most recent assistant message over earlier ones in the thread.
ANSWER_BODY = "div[data-renderer='lm']"

# Citation chips (verified 2026-08-17): each inline citation is a `<span class="citation-nbsp">`
# (a nbsp spacer) immediately followed by a `<span data-pplx-citation="" ...>` wrapping the
# domain-name chip (e.g. "reuters", optionally "+N" for grouped sources). `data-pplx-citation` is
# a deliberate semantic marker, unlike the churny Tailwind classes around it. Currently unused by
# `extract_answer` (which copies markdown via the Copy button and strips citations from the
# string) but kept as verified knowledge for any future DOM-text path.
CITATION_NODES = "[data-pplx-citation], .citation-nbsp"

# The answer action bar's copy control: copies the answer as markdown. The action bar sits
# *below* the answer body, so `.last` lands on the latest message's copy even when earlier
# answers (or embedded code-block copy controls) match the same aria-label.
COPY_BUTTON = "button[aria-label='Copy']"


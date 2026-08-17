"""DOM selectors and constants for the Google Flow web app.

Verified 2026-08-14 against a live, logged-in session (account UI rendered in Vietnamese).
Key findings that shaped these selectors:

- The app has NO `data-testid` or `aria-label` attributes on most controls, and its CSS
  class names are per-build styled-components hashes (unstable). The one stable, locale-
  independent anchor is the *Material Symbols icon ligature name* rendered as element text
  (e.g. "add_2", "arrow_forward", "tune") — these stay in English regardless of the
  account's UI language.
- The public marketing page (`labs.google/flow`) requires no login and is NOT a valid
  "is the user logged in" signal. The real, auth-gated app lives at `labs.google/fx/tools/flow`
  (redirects to a locale-specific path, e.g. `/vi/tools/flow`, once authenticated; redirects to
  `accounts.google.com` if not).
- There is no separate "switch to image mode" tab — the default UI is already an agent-style
  prompt box that creates images/video based on the prompt + the settings below.
- The prompt input is a `[role="textbox"]` contenteditable `<div>`, not a `<textarea>`.
- Generation parameters (model, aspect ratio, count) are configured via a "tune" (Settings)
  icon button that opens a side panel with aspect-ratio buttons ("16:9", "4:3", "1:1", "3:4",
  "9:16"), count buttons ("x1".."x4"), and a model dropdown (default seen: "Nano Banana 2").
- Flow has a "confirm before creating" setting (default: always confirm), but no confirmation
  dialog was actually shown during a real, successful submission — it may only apply to
  video generation or a different account tier. `SUBMIT_BUTTON` and typing via an explicit
  `.click()` before `human_type` (see `prompt.py`) are verified: a real image ("a red apple on
  a wooden table") was successfully generated end-to-end on 2026-08-14.
- The completed generated image is an `<img>` whose `src` matches
  `/fx/api/trpc/media.getMediaUrlRedirect?name=<uuid>` — a stable backend API path, unlike its
  CSS classes (also shared with the unrelated user-avatar `<img>`, so those can't be used
  alone). NOTE: each generated image appears **twice** in the DOM (once in the main canvas,
  once in the agent chat log) with the *same* `src` — downstream code must dedupe by URL.
"""

from __future__ import annotations

# Public marketing page — reachable without login, NOT a valid auth check.
FLOW_MARKETING_URL = "https://labs.google/flow"

# The real, auth-gated app entry point. Redirects to a locale-specific path when
# authenticated (e.g. ".../vi/tools/flow") and to accounts.google.com when not.
FLOW_URL = "https://labs.google/fx/tools/flow"

# Substring present in the URL when Google redirects an unauthenticated session to sign-in.
LOGIN_REDIRECT_HOST = "accounts.google.com"

# --- Verified against a live session ---
NEW_PROJECT_BUTTON = "button:has-text('add_2')"
SETTINGS_BUTTON = "button:has-text('tune')"
PROMPT_TEXTBOX = "[role='textbox']"
SUBMIT_BUTTON = "button:has-text('arrow_forward')"
RESULT_IMAGE_THUMBNAIL = "img[src*='media.getMediaUrlRedirect']"

# Existing-project cards on the Flow home page (a virtualized list, most-recent-first); each
# wraps an <a href=".../tools/flow/project/<uuid>"> around a thumbnail. Verified 2026-08-15
# against real DOM markup — CSS classes are per-build hashes (unstable), so only the href
# substring is used, same convention as the other selectors above.
PROJECT_LINK = "a[href*='/project/']"

# Project deletion (§6.2). The delete trigger is a button carrying a Material Symbols
# "delete" icon ligature, scoped to the <i> so the localized sr-only <span> can't false-match.
# The confirmation dialog is a generic role=dialog/alertdialog; its confirm button is matched
# by known label text rather than by copying the trigger's sr-only label (tried and rejected:
# a freshly-created project's trigger can momentarily render that label in the wrong locale)
# or by position (fragile if the dialog ever gains a third button). Extend this tuple as new
# locales are observed live; matching is case-insensitive substring (verified 2026-08-15: "Hủy"
# for cancel, "Xoá dự án" for confirm).
CONFIRM_BUTTON_LABELS = ("delete", "xoá dự án", "xóa dự án")
PROJECT_DELETE_BUTTON = "button:has(i.google-symbols:text-is('delete'))"
CONFIRM_DIALOG = "[role='dialog'], [role='alertdialog']"

# --- Unverified: reference-image upload and error states were not exercised live ---
REFERENCE_UPLOAD_INPUT = "input[type='file']"
ERROR_BANNER = "[role='alert']"

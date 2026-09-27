"""DOM selectors and constants for the Google Flow web app.
"""

from __future__ import annotations

# Public marketing page — reachable without login, NOT a valid auth check.
FLOW_MARKETING_URL = "https://flow.google.com/about"

# The real, auth-gated app entry point. Redirects to a locale-specific path when
# authenticated (e.g. ".../vi/tools/flow") and to accounts.google.com when not.
FLOW_URL = "https://flow.google.com"

# Substring present in the URL when Google redirects an unauthenticated session to sign-in.
LOGIN_REDIRECT_HOST = "accounts.google.com"

# --- Verified against a live session ---
# Verified 2026-09-06: Flow changed the new-project Material icon from `add_2` to `add`.
# Material icon ligatures remain English even when Flow's visible UI is localized.
NEW_PROJECT_BUTTON = "button:has(mat-icon:has-text('add'))"
SETTINGS_BUTTON = "button:has(mat-icon:has-text('tune'))"
FLOW_SETTINGS_VIEW = "flow-settings-view"
SETTINGS_BUTTON_TOGGLE_GROUP = "flow-toggles"
MODEL_BUTTON = "button .model-select-trigger-label"
CDK_OVERLAY_DROPDOWN = "div.cdk-overlay-pane"
PROMPT_TEXTBOX = "flow-rich-text-editor.prompt-input div[contenteditable='true']"
SUBMIT_BUTTON = "flow-generate-icon-button button:has(mat-icon:has-text('arrow_forward'))"
RESULT_IMAGE_THUMBNAIL = "flow-grid-tile-container flow-image-tile img"

# Existing-project cards on the Flow home page (a virtualized list, most-recent-first); each
# wraps an <a href=".../tools/flow/project/<uuid>"> around a thumbnail. Verified 2026-08-15
# against real DOM markup — CSS classes are per-build hashes (unstable), so only the href
# substring is used, same convention as the other selectors above.
PROJECT_LINK = "a[href*='/project/']"


HEADER_MENU_BUTTON = "#flow-desktop-header button[aria-haspopup='menu']"
DELETE_MENU_ITEM = "button[role='menuitem']:has(i:text-is('delete'))"
CONFIRM_BUTTON_LABELS = ("delete", "xoá dự án", "xóa dự án")
CONFIRM_DIALOG = "[role='dialog'], [role='alertdialog']"

# --- Unverified: reference-image upload and error states were not exercised live ---
REFERENCE_UPLOAD_INPUT = "input[type='file']"
ERROR_BANNER = "[role='alert']"

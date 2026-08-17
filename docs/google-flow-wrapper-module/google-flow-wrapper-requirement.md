 Google Flow Wrapper — Requirements & Technical Solution

**Version:** 0.1 (MVP)  
**Date:** 2026-08-14  
**Status:** Draft  

---

## 1. Overview

### 1.1 Purpose
Build a Python module that wraps the Google Flow web application (https://labs.google/flow) into a reliable, callable interface (CLI + library). The module allows users and backend systems to send text prompts, wait for generation, and receive generated images while managing multiple Google accounts safely and efficiently.

### 1.2 Goals
- Turn the interactive web UI into a programmable API and CLI.
- Support multiple Google accounts with persistent sessions.
- Rotate requests across accounts to reduce risk of rate-limiting or account flags.
- Provide a clean, importable interface that can later be wired into any backend service.
- Prioritize reliability, session reuse, and ease of account management in the MVP.

### 1.3 Scope (MVP)
**In scope**
- Image generation only (Nano Banana / Imagen family models inside Flow).
- Multi-account support with easy add/remove.
- Session persistence and reuse.
- Round-robin (or simple load-balanced) request rotation.
- CLI + Python library interface.
- Anti-detection browser automation.

**Out of scope (MVP)**
- Video generation (Veo).
- Advanced editing features (inpainting, ingredients-to-video, camera control, etc.).
- Official Google API integration (none currently exists for Flow).
- Distributed multi-machine orchestration.
- Full CAPTCHA solving service integration (basic hooks only).

---

## 2. Functional Requirements

### 2.1 Core Generation
| ID | Requirement | Priority |
|----|-------------|----------|
| FR-01 | Accept a text prompt and optional parameters (model, aspect ratio, number of images). | Must |
| FR-02 | Submit the prompt to Google Flow, wait for generation to complete, and return the resulting image(s). | Must |
| FR-03 | Support downloading images as local files, bytes, or URLs. | Must |
| FR-04 | Handle generation timeouts, failures, and retries gracefully. | Must |
| FR-05 | Allow optional reference images (upload) for image-to-image style generation when supported by the UI. | Should |

### 2.2 Multi-Account Management
| ID | Requirement | Priority |
|----|-------------|----------|
| FR-06 | Support multiple Google accounts simultaneously. | Must |
| FR-07 | Provide simple CLI and API methods to **add** an account (interactive login recommended for first-time). | Must |
| FR-08 | Provide simple CLI and API methods to **remove** an account (including its stored session). | Must |
| FR-09 | Allow enable / disable of accounts without deleting them. | Should |
| FR-10 | Support forced re-login when a session expires or becomes invalid. | Must |
| FR-11 | Persist browser sessions (cookies + storage) so accounts remain logged in across process restarts. | Must |
| FR-12 | Isolate each account in its own browser context / profile. | Must |

### 2.3 Request Rotation & Concurrency
| ID | Requirement | Priority |
|----|-------------|----------|
| FR-13 | Rotate requests across available accounts using round-robin (MVP) or least-loaded strategy. | Must |
| FR-14 | Limit concurrent jobs per account (configurable, default 1). | Must |
| FR-15 | Skip accounts that are disabled, in cooldown, or marked as needing login. | Must |
| FR-16 | Track basic per-account metrics (success/fail counts, last used). | Should |

### 2.4 Interface
| ID | Requirement | Priority |
|----|-------------|----------|
| FR-17 | Expose a clean Python library API (`FlowClient`). | Must |
| FR-18 | Provide a CLI (e.g. via Typer) for generation and account management. | Must |
| FR-19 | Support both async and sync usage patterns. | Should |
| FR-20 | Allow configuration via YAML/JSON file and environment variables. | Must |

### 2.5 Observability & Resilience
| ID | Requirement | Priority |
|----|-------------|----------|
| FR-21 | Structured logging of all major actions and errors. | Must |
| FR-22 | Health-check command that verifies accounts are still logged in and usable. | Should |
| FR-23 | Automatic status update (e.g. mark account as `needs_login` on repeated auth failures). | Should |

---

## 3. Non-Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| NFR-01 | Use an anti-fingerprint / stealth browser (Camoufox preferred, or equivalent). | Must |
| NFR-02 | Support residential / mobile proxies per account. | Should |
| NFR-03 | Human-like interaction patterns (delays, mouse movement, typing). | Should |
| NFR-04 | Sessions and account metadata stored locally under a configurable data directory. | Must |
| NFR-05 | Module must be installable as a standard Python package. | Must |
| NFR-06 | Code should be readable and modular so it can later be extended for video or backend workers. | Must |
| NFR-07 | Respect reasonable rate limits; avoid aggressive concurrent hammering of a single account. | Must |

---

## 4. High-Level Technical Solution

### 4.1 Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        User / Backend                        │
│              (CLI  or  Python import  or  API)               │
└────────────────────────────┬────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────┐
│                      FlowClient (Public API)                 │
│  - generate_image() / generate_batch()                       │
│  - accounts.add() / remove() / list() / health()             │
└────────────┬───────────────────────────────┬────────────────┘
             │                               │
┌────────────▼────────────┐     ┌────────────▼────────────────┐
│   AccountManager        │     │   Job / Rotation Engine      │
│  - accounts.yaml        │     │  - Round-robin / least-load  │
│  - session isolation    │     │  - Per-account semaphores    │
│  - status tracking      │     │  - Queue (optional)          │
└────────────┬────────────┘     └────────────┬────────────────┘
             │                               │
┌────────────▼───────────────────────────────▼────────────────┐
│              Browser Automation Layer                        │
│  Camoufox (preferred) / Playwright + stealth                 │
│  - Persistent storage_state per account                      │
│  - Proxy support                                             │
│  - Humanized actions                                         │
└────────────────────────────┬────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────┐
│                    Google Flow Web UI                        │
│              https://labs.google/flow                        │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 Key Components

**1. AccountManager**
- Maintains `accounts.yaml` (or equivalent) containing email, label, proxy, status, metrics.
- Each account has its own directory under `data/sessions/<email>/` holding `storage_state.json`.
- Responsibilities: add, remove, enable/disable, relogin, get_next_available().

**2. Browser Layer**
- Preferred: **Camoufox** (Firefox-based, engine-level fingerprint spoofing, Playwright-compatible).
- Fallback: Patchright / CloakBrowser / nodriver.
- One persistent context (or user-data-dir) per account.
- Launch headed for first-time login; headless for normal operation.
- Optional residential proxy bound to the account.

**3. Generation Flow (per job)**
1. Select next available account via rotation logic.
2. Load its stored session into a browser context.
3. Navigate to Flow → ensure correct project / image mode.
4. Enter prompt (and optional references).
5. Trigger generation.
6. Poll for completion (DOM or network).
7. Download / extract image(s).
8. Update account metrics and release lock.
9. Return results to caller.

**4. Public Interfaces**
- **Library**: `FlowClient` class with async methods.
- **CLI**: `flow generate ...`, `flow account add|remove|list|health|relogin ...`

### 4.3 Account Add / Remove (MVP UX)

**Add account**
```bash
flow account add user@gmail.com --label "main" --proxy "http://..."
```
- Creates entry with status `needs_login`.
- Opens headed browser.
- User completes Google login (including 2FA if required).
- Module detects successful Flow access, saves `storage_state.json`, marks account `active`.

**Remove account**
```bash
flow account remove user@gmail.com
```
- Deletes entry from `accounts.yaml` and removes the entire session directory.

**Other helpers**
- `flow account list`
- `flow account disable / enable`
- `flow account relogin <email> --headed`
- `flow account health`

### 4.4 Data Layout (MVP)

```
data/                          # configurable root
├── accounts.yaml              # account registry + metadata
├── sessions/
│   ├── user1@gmail.com/
│   │   └── storage_state.json
│   └── user2@gmail.com/
│       └── storage_state.json
└── outputs/                   # optional default image output dir
```

### 4.5 Technology Stack (Recommended)

| Layer              | Choice                          | Notes                                      |
|--------------------|---------------------------------|--------------------------------------------|
| Language           | Python 3.11+                    | Async-first                                |
| Browser            | Camoufox (primary)              | Best current open-source stealth           |
| Automation API     | Playwright-compatible           | Via Camoufox                               |
| CLI                | Typer                           | Clean, typed CLI                           |
| Config / Models    | Pydantic + YAML                 | Validation + easy serialization            |
| Async              | asyncio                         | Native                                     |
| Image handling     | Pillow / aiofiles               | Save & post-process                        |
| Logging            | structlog or standard logging   | Structured logs                            |

### 4.6 Security & Risk Notes
- Stored sessions contain authentication cookies → protect the data directory (file permissions or optional encryption with a master key).
- Automating Google services can violate Terms of Service and may result in account restrictions. Use responsibly, keep concurrency low, and prefer residential proxies.
- Interactive first-time login is deliberately chosen to reduce detection risk compared with fully automated credential stuffing.

---

## 5. Future Extensions (Post-MVP)

- Video generation support (Veo).
- Credit / quota scraping and intelligent account selection.
- Distributed workers with Redis / RabbitMQ.
- Web dashboard for account status and job monitoring.
- Automatic CAPTCHA solving integration.
- Project and asset management inside Flow.
- Official API fallback if Google ever releases one.

---

## 6. Success Criteria for MVP

- [ ] Can add at least two Google accounts via CLI with interactive login.
- [ ] Sessions survive process restart and can be reused headlessly.
- [ ] `generate_image(prompt)` successfully returns one or more images.
- [ ] Requests are rotated across accounts (no single account receives all traffic).
- [ ] Accounts can be removed cleanly.
- [ ] Basic CLI and Python import both work.
- [ ] Failures are logged and accounts can be marked unhealthy automatically.

---

**Document owner:** TBD  
**Next step:** Detailed design / skeleton implementation of `AccountManager` + `FlowClient`.
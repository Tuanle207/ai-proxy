# ADR-001 — Provider Seam

- **Status:** Accepted
- **Date:** 2026-08-16
- **Deciders:** multi-provider refactor (§2.1 of `multi-provider-refactor-plan.md`)

## Context

`google_flow_wrapper` hard-wires a single destination (Google Flow) throughout its core
machinery: the worker engine instantiates `GenerationRunner`, the service container owns a single
`AccountManager`/`AccountSlotPool`, and the DB schema has Flow-shaped columns (`model`,
`aspect_ratio`, `overlay_logo`, `project_id`). Adding a second provider (Perplexity, then
"the next one") would otherwise mean `if provider == ...` branches in every layer, or forking the
whole package.

## Decision

We introduce a **provider plugin seam** with four binding decisions:

1. **Adapter over inheritance.** A provider is a `ProviderAdapter` (a `Protocol` with `execute`,
   `classify_failure`, `health_check`, `cleanup`) plus a declarative `ProviderSpec`. Core's
   `TaskRunner` owns the session lifecycle (account slot, browser context, timing, persistence,
   events); the adapter only drives *one destination*. No provider subclasses core classes.

2. **Per-provider account registries.** `AccountManager` is constructed per provider and reads
   `data/providers/<provider>/accounts.yaml`. Status, cooldowns and `storage_state.json` are
   per-site facts; the same email on Flow and Perplexity must not share them.

3. **Opaque `params` JSON.** Anything provider-specific that must be persisted goes into
   `jobs.params` / `jobs.provider_state` (JSON), validated against the provider's `params_model`.
   No new core column is added per provider.

4. **No core → provider imports.** `core/` may never import `ai_proxy.providers.*`. Providers may
   import `core/` freely; siblings must not import each other. Providers self-register into a
   registry; core resolves them by name at runtime.

## Consequences

- The provider seam is mechanically enforced (import-linter / pytest AST guard, `lint-imports`).
- Phases 1–4 carry a *temporary* core→provider import until Phase 5 re-interfaces the Flow body
  behind `ProviderAdapter`; the contract is enforced in CI at Phase 10.3, once it holds.
- The data model generalizes from "image generation" to typed tasks (`TaskKind`) and artifacts
  (text/image/video/file), so a non-browser or non-image provider needs no schema change.
- Pre-1.0, no backward compatibility is preserved; the import root moves to `ai_proxy` in one
  breaking change.

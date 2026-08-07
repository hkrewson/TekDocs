# TekDocs Engineering Instructions

These instructions apply to the entire repository. More specific instructions in `backend/AGENTS.md` and `frontend/AGENTS.md` add subsystem invariants.

## Before changing code

1. Read `docs/PRODUCT_CHARTER.md`, `docs/ROADMAP.md`, the relevant ADRs under `docs/adr/`, and `docs/SECURITY.md` for security-sensitive work.
2. Name the current roadmap slice and its acceptance criteria before editing. Do not silently expand it.
3. Inspect the working tree. Preserve unrelated and user-owned changes.

## Delivery rules

- Treat Django migrations as the sole database schema authority. Do not create a parallel initialization schema.
- Keep implementation, migrations, OpenAPI, tests, architecture documentation, roadmap status, and release notes aligned.
- Distinguish `verified`, `inferred`, and `blocked` in closeout notes. Docker evidence is required for runtime claims.
- Never put real credentials, fixed access tokens, customer identifiers, or private data in source, fixtures, logs, screenshots, commands, or uploaded artifacts.
- Do not push, publish, tag, deploy, or alter external systems without explicit authorization.
- A completed roadmap slice should be one descriptive commit. Do not commit incomplete or unrelated work merely to make the tree clean.
- Security and data-integrity work may preempt feature work. Dates never justify skipping authorization, backup, migration, or release gates.

## Required closeout

A slice is complete only when its code, migration path, API contract, positive and negative tests, Docker runtime evidence, docs, and known-risk disposition agree. Run the strongest relevant `make` gate. If a gate cannot run, report exactly why and which hosted gate must confirm it.

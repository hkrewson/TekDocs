# TekDocs Engineering Instructions

These instructions apply to the entire repository. More specific instructions in `backend/AGENTS.md` and `frontend/AGENTS.md` add subsystem invariants.

For release status, evidence, CI failures, or operator acceptance, read `planning/releases/README.md` and use the pinned candidate manifest before historical review notes.

## Before changing code

1. Read `README.md`, these instructions, the relevant subsystem instructions, and the public GitHub Wiki when it is available.
2. Name the current roadmap slice or issue and its acceptance criteria before editing. Do not silently expand it.
3. Inspect the working tree. Preserve unrelated and user-owned changes.

## Delivery rules

- Local Docker is the development environment. Reuse the single `tekdocs`
  Compose project for development and testing, using `docker compose exec`
  against existing containers. Rebuild/recreate its services in place when
  required; do not create parallel projects, per-run containers, acceptance
  stacks, rehearsal stacks or additional data volumes by default.
- Before running a Make target or test script locally, inspect whether it uses
  `docker compose run`, creates a new project, or provisions another database
  service. Adapt execution to the existing development containers. If a gate
  genuinely requires a separate environment or would destroy retained data,
  report that constraint and leave it to hosted CI unless the user explicitly
  authorizes that specific local exception. Do not silently create disposable
  stacks even if a script or skill recommends them. Keep test database state
  separate from retained development records within the existing database service.

- Treat Django migrations as the sole database schema authority. Do not create a parallel initialization schema.
- Keep implementation, migrations, OpenAPI, tests, architecture documentation, roadmap status, and release notes aligned.
- Distinguish `verified`, `inferred`, and `blocked` in closeout notes. Docker evidence is required for runtime claims.
- Reproduce a reported failure before changing code to fix it, and name the reproduction in the closeout. A cause read off an error message is a hypothesis, not a diagnosis. This binds hardest on test-only changes, where loosening a selector or an assertion can retire the symptom while leaving the defect in place.
- Suspect the harness when a failure names a column, table, or fixture that the change under review never touched. Schema and privilege state leaking between tests presents as a missing migration.
- Never put real credentials, fixed access tokens, customer identifiers, or private data in source, fixtures, logs, screenshots, commands, or uploaded artifacts.
- Do not push, publish, tag, deploy, or alter external systems without explicit authorization.
- Explicit authorization to push a versioned release to `main` covers the single-push CI pipeline's image publication, application/receipt tags, verification and evidence delivery. Do not request separate approval for those stages of the same release. Production deployment remains separate. Complete receipt delivery in CI; never leave it as an operator-requested follow-up. Required source review and risk decisions precede the release push. See `planning/releases/ci-release-delivery.md`.
- A completed roadmap slice should be one descriptive commit. Do not commit incomplete or unrelated work merely to make the tree clean.
- Security and data-integrity work may preempt feature work. Dates never justify skipping authorization, backup, migration, or release gates.

## Required closeout

A slice is complete only when its code, migration path, API contract, positive and negative tests, Docker runtime evidence, required Wiki change, and known-risk disposition agree. Run the strongest relevant `make` gate. If a gate cannot run, report exactly why and which hosted gate must confirm it.

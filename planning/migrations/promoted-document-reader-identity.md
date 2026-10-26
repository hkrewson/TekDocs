# Promoted document reader identity regression

October 25, 2026. Bounded #105 follow-up to the 0.9.14 production smoke.

## Scope and acceptance

Opening a promoted document from Documentation must read the same indexed Git
content as the repository reader, and its repository-editor link must select
the corresponding document root. Preserve the public document entity identity,
Workspace authorization, stale-index rejection and refusal to show a database
copy. No migration, authority transition, dependency change or production
content repair is part of this correction.

## Reproduction and diagnosis

The operator reported a Git-unavailable error in Documentation and two
same-title repository entries: a document root with an empty raw body and a
fragment containing the text. Only synthetic identifiers/content are used here.

Docker reproduction, before changing runtime code:

```bash
docker compose exec -T migrate pytest apps/core/tests/test_document_migration_inventory.py::test_mixed_authority_browse_retains_legacy_documents -q --tb=short
```

The fixture creates and imports a synthetic legacy document, indexes and promotes
it, then replays the Documentation client by taking the public `id` from the
search response and calling the content-graph detail route. It failed
`assert 404 == 200` with `No ContentNode matches the given query`. The index had
already been successfully built. A separate UI regression failed because the
reader was called with the public entity ID instead of the distinct content ID.
This reproduces the reported read failure without requiring production access.

The public document API serializes `id` from `Document.entity_id`. Migration
exports its Git root using `Document.id`, which is also the indexed node's
`content_id`. The browser used the former for a route requiring the latter;
the editor link made the same substitution. This is an identity mismatch,
not evidence of a stale production index or lost text.

The existing repository UI lists files by kind and path. A document root and
its included reusable fragment are separate parts, not revision copies. The
synthetic regression verifies that an empty raw root body plus an include
resolves to nonempty rendered text. The production entry types/paths reported
by the operator match that shape; production composition has not been inspected.

## Correction and contract

Document responses now expose read-only `content_id` alongside the unchanged
public `id`. The browser uses it for Git reads and the repository-editor link.
Missing identity or unavailable content still fails closed; the client does
not guess an ID or display the historical database body. OpenAPI and generated
TypeScript are regenerated. No database migration is required.

The regression checks distinct IDs, composed content from an empty root,
wrong-ID and wrong-Workspace rejection, and a stale-index 409 with no body leak.
UI tests cover MSP and organization scopes, the editor link, failed reads and
missing identity. Existing browse count/filter/pagination checks remain intact.
The Wiki draft explains document/fragment entries; ADR 0115 records the identity
boundary. No extra authority or permission is granted.

## Validation and limits

Verified: the post-fix Docker regression passed. The `test-document-migration-inventory`
selection passed all 29 tests, including runtime RLS. The `test-content-read`
selection passed 104 tests, including composition, Workspace reads and the
accepted-Git upgrade case. Five API-contract tests passed. These Make selections
were executed with `docker compose exec -T migrate pytest ... --reuse-db` instead
of their `compose run` commands, preserving the test selections and using only
the existing database service. Local logs are `/tmp/tekdocs-read-inventory.log`,
`/tmp/tekdocs-reader-content.log` and `/tmp/tekdocs-reader-api.log`.

All 774 frontend tests passed with the existing coverage thresholds. A new test's
method-reference lint failure was corrected using the existing spy-access pattern;
final API generation check, lint, type checking and production build passed,
including bundle budgets. The focused missing-identity retest passed. Initial type checking found stale local
Playwright installation metadata; reinstalling the committed lockfile corrected
the tooling without dependency changes. A fixture initially created a client
after indexing, which legitimately advanced the MSP repository head; moving that
prerequisite before indexing preserved the stale-index assertions and restored
the fixture. No assertion or security rule was relaxed.

Ruff and mypy passed (270 source files). Django reported no migration changes.
Docker schema generation completed with zero errors and four existing operation-ID
warnings. The first schema generation exposed stale ignored local package metadata;
installing the current package in the existing service corrected the version
before retaining the generated contract. Wiki page/link validation and all 120
tooling checks passed (three optional tooling checks skipped).

The existing `tekdocs` Compose project's migration service is reused for test
execution with an idle command and source mount. Tests use their separate
PostgreSQL test database within the existing database service. No separate
project, database service, runtime volume or production mutation is introduced.
The test service is restored to its ordinary stopped configuration afterward.

The full document-migration release gate includes separate upgrade/image
rehearsals and is deferred to hosted CI under the repository's local-container
policy. Exact-candidate hosted Build, CodeQL, browser and release validation
remain required before publication. This patch is not a published release or
a claim of production verification. No new known security exception is proposed.

Inferred: fixing the reproduced browser/API identity mismatch restores this
production reader because the same route and response identities are used.
Blocked pending deployment: confirming the specific production guide opens
and its editor link selects the document root. Additional authority transitions
and the publication-bearing guide's eligibility remain outside this scope.

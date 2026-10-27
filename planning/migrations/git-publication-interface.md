# Git-backed ordinary publication interface

October 27, 2026. Bounded #106 interface follow-up to
[publication-history migration](publication-history-migration.md).

## Acceptance and behavior

An authorized staff member can open a supported promoted ordinary document,
publish a permanent internal snapshot, publish a correction, withdraw a retained
publication, inspect its decisions and download its retained PDF. The document
has one owned fragment, no managed files, templates or unsupported dependencies,
a current accepted/indexed Git source and intact supported publication history.
The existing review, permission, MFA, tenant and client boundaries apply.

**Publish document** is available once the Git reader loads. Its form fixes the
audience to MSP staff and retention to permanent. The standard document preflight
now pins the accepted repository source and uses the publisher's content,
review and retained-custody gates. It returns the existing preflight response
shape and a value-free blocker for unavailable or unsupported sources. It never
resolves the legacy draft. Publishing independently rechecks source and policy;
a successful preflight is not authorization or a reserved publication.

**Publication history** opens retained legacy and Git versions from the document
reader, with an empty state and keyboard focus. The view supports the existing
`document_view=publications` document link. Each retained version opens the same
content/downloads/decisions interface. Corrections append snapshots, withdrawal
appends a decision, and prior signatures, content and PDFs remain unchanged.
The original draft revision history is still separate and unavailable for
Git-authoritative documents. Raw Git editing uses the existing repository editor.

No schema, permission, signing format, source authority or release version changes.
No new authority-management interface is introduced. Broader files/templates,
keys/references, client delivery and broad #105/#106 acceptance remain open.

## Reproduction and validation

Before implementation, the new API test reproduced HTTP 409 from a promoted
document's preflight. The new browser test reached current Git content but could
not find **Publish document** at 320px or 1440px. Those are the API and browser
reproductions for this slice.

Validation uses the existing `tekdocs` Compose project. The existing idle migrate
service runs official Django test settings against a separate PostgreSQL test
database; the existing frontend service temporarily runs its matched browser/Node
tooling image. No second project, service, volume or disposable stack is created.
The pre-existing local Valkey restart fault remains outside this slice.

Browser tests use synthetic HTTP fixtures to exercise the real interface and
browser download handling. API tests use real PostgreSQL, managed Git, publication
signing and generated PDFs. These complementary tests do not claim a live browser
journey against an upgraded or production installation.

### Verified

- The 152-test focused Docker suite passes: Git publications, migration inventory,
  retained-history migration, ordinary documents, publication read failures,
  runtime RLS and API contracts. The real API lifecycle test signs current Git
  text, creates a correction, withdraws it, and compares the original retained
  content, signature and generated PDF bytes after those operations.
- The adapted `test-publication-control` backend gate also passes: 1,680 checks,
  with one existing empty-parameter selection skipped in the malformed-UUID
  route matrix. This includes custom roles, the full authorization matrix and
  migration stabilization. The isolated final runtime-role check verifies the
  new preflight before/after publishing as owner and read-only staff, plus a
  retained PDF download under the read-only runtime principal.
- One premature runtime check overlapped the normal test database's deliberate
  downgrade and failed on its older schema. That result was discarded. The
  final check used a different test database in the existing PostgreSQL service,
  passed, and dropped that database. No production or retained development
  records were used or changed.
- The complete frontend unit run passes (127 test files, zero failed files),
  with the affected 67-test Documentation suite rerun after the final interface change,
  together with ESLint, TypeScript, generated API checking, production build and
  compressed bundle budgets.
- All 12 new browser checks pass across Chromium, Firefox and WebKit. The 84
  existing publication/draft/repository-layout/direct-link checks also pass. The positive
  journey runs at 320px and 1440px and checks accessibility and overflow; negative
  journeys cover unsupported content, failed preflight and an unavailable Git
  reader while retained history remains readable. Rejected publish/withdraw
  operations retain reason text.
- WebKit's initial download failure was reproduced independently: identical
  `route.fulfill` PDF attachments emit no download event, while a real HTTP
  response does. Only the synthetic PDF fixture now uses HTTP in the existing
  browser container; the test still follows the exact document/publication PDF
  route and asserts the browser download event and filename.
- Ruff and mypy pass (272 backend source files); no migrations are generated.
  OpenAPI regenerates byte-identically with zero errors and four existing
  operation-ID warnings. Wiki links, product/language/responsive contracts,
  version consistency, supply-chain pins and Compose configuration pass.

### Inferred and blocked locally

The browser tests verify interface behavior with synthetic responses; real API
and runtime-role checks verify server behavior separately. A complete browser
journey against a migrated installation remains unverified. Hosted
upgrade/recovery/image rehearsals remain required for release acceptance: their
scripts create additional environments and cannot run locally under the
single-project instruction. No version bump, production deployment or production
authority change is part of this slice. Production remains 0.9.15.

### Source review

The shared readiness helper preserves the publisher's existing accepted-source,
shape, review and custody gates. The view authorizes the exact document before
checking readiness; publish, correction, withdrawal and download retain their
existing server policy checks. No new grant, dependency, schema, signing format,
mutable publication path or unsafe HTML sink is introduced. Current unsupported
shapes stay blocked. Existing release risk decisions are not renewed by this
unreleased interface change.

## Unreleased notes

- Connect supported promoted Git-backed documents to internal publishing and
  permanent retention through a Git-aware readiness check.
- Expose retained legacy/Git publication history from the document reader, with
  correction, withdrawal, decision history and protected PDF downloads.
- Preserve reason text after rejected operations and keep unavailable or
  unsupported Git content blocked without database fallback.

Public Wiki operator instructions are drafted in the separate Wiki checkout;
existing unrelated Wiki edits are preserved and are not included in the source
commit or automatically published.

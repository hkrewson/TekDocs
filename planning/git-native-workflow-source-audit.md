# Clean-start Git-native workflow source audit

Audit date: November 2, 2026. Source: `64bb580534e326717dcb725594316d995b511947`
plus the current local planning/exporter changes. This is a read-only source/test
inventory, not a fresh runtime pass or a report of reproduced application defects.
The six deferred legacy automatic-migration shapes remain outside this audit.

## Key distinction

A document migrated to Git can retain a legacy `Document` row. A newly authored
repository document need not have one. Passing migration/publication journeys
therefore does not establish a complete clean-start interface. The canonical
managed authoring path checks an existing row but does not require one
([author_content](../backend/apps/core/content_authoring.py:263)). Legacy routes
resolve by that row before dispatching any Git behavior
([_document](../backend/apps/core/document_views.py:202)).

## Finite implementation/acceptance queue

| Item | Source finding | Required bounded next proof |
| --- | --- | --- |
| Native discovery and manual-export completeness | Ordinary document search derives repository IDs from authority rows and then narrows them through legacy `Document` records ([search](../backend/apps/core/document_views.py:366)). Native content remains available through repository listing, but a no-legacy-row document is not added to this ordinary search result. The local exporter enumerates only that search endpoint ([export loop](../scripts/export_documents_markdown.py:125)); its native fallback cannot discover a document the list omitted. Synthetic mixed-list tests assume such an entry is returned and do not establish real API enumeration parity. | Reproduce a native-only document alongside an older document; make discovery and export account for both, deduplicate by exact Workspace/content identity, and fail visibly on incomplete enumeration. Do not approve a manual copy from a success count alone. |
| Native publication lifecycle through the interface | Repository editor exposes saved exports and read-only publication history, not publish/correct/withdraw controls ([panel](../frontend/src/documentation/RepositoryContentPanel.tsx:350), [history](../frontend/src/documentation/RepositoryPublicationHistory.tsx:99)). The generic document client publishes and withdraws through legacy-document routes ([client](../frontend/src/documentation/api.ts:695)). Native repository evidence, review, package authorization, STATIC publication, controls and delivery **already have backend routes** ([views](../backend/apps/core/repository_publication_views.py:778), [STATIC/control/delivery](../backend/apps/core/repository_publication_views.py:999)); do not rebuild or declare that backend absent. | Reproduce the clean-created document journey, then connect one supported UI path through publish, corrections/supersession, withdrawal, retained history/PDF and authorized portal delivery. Prove denials, integrity errors and drafts remain safe. |
| New Git-backed field/content key bindings | Managed authoring explicitly excludes `key_bindings` from editable metadata ([allowlist](../backend/apps/core/content_authoring.py:44), [validation](../backend/apps/core/content_authoring.py:191)); the focused test expects rejection ([test](../backend/apps/core/tests/test_content_authoring.py:58)). The binding API first requires a legacy document and refuses mutations after Git handoff ([lookup](../backend/apps/core/document_key_views.py:75), [write gate](../backend/apps/core/document_key_views.py:123)). Native evidence retention also explicitly rejects keys when no legacy document exists ([gate](../backend/apps/core/repository_publication_evidence.py:199)). | Provide or explicitly scope a safe native binding-authoring and publication-freeze path; prove field and content substitution, missing/denied targets, frozen values and cross-client isolation on a freshly created Git document. This is current authoring support, not import of parameterized foreign legacy bodies. |
| Native template enrollment | Template instantiation resolves a legacy source `Document` before selecting its Git implementation ([instantiate](../backend/apps/core/document_views.py:823)). The Git branch is support for a retained source row, not evidence that a repository-only template can enroll. Portable metadata supports `template_sources` ([profile](../backend/apps/core/content_profile.py:42)), so lower composition support must not be confused with enrollment controls. | Reproduce new source-template creation and enrolled client-document creation without legacy preparation; connect the existing template semantics to a supported native route and interface, then prove live/pinned/copy, update review and isolation. |
| Native monitored-source configuration | Source lookup and settings first resolve a legacy document, and source rows are keyed to it ([lookup/settings](../backend/apps/core/document_source_views.py:27)). Git observation apply on a promoted row is a different capability. | Reproduce configuration on a fresh Git document; establish supported settings, check/observations, local-edit protection and reviewed apply without requiring a legacy import. |
| Native primary-file versions in the interface | Native primary-file GET/POST version routes **exist** ([append](../backend/apps/core/content_authoring_views.py:421), [routes](../backend/apps/core/content_authoring_views.py:445)). The repository editor currently exposes ordinary attachments only ([controls](../frontend/src/documentation/RepositoryContentPanel.tsx:340)); the legacy replacement route requires `_document` ([replacement](../backend/apps/core/document_views.py:1169)). | Verify native file APIs and connect version creation/history/download to the clean-start interface. Exercise stale-current conflicts, scanned intake, publication retention and file isolation. Do not duplicate the existing custody implementation. |

These are source-inferred current-workflow gaps and targeted reproduction tasks.
They are not six freshly reproduced runtime failures and not automatic authority
to implement all six in one patch. Confirm the intended native path before each
bounded fix; tests may expose a missing adapter rather than a missing capability.

## Source coverage that should be reused

- Native create/read/update/move, conflict handling, ordinary scanned attachment
  upload/download, editable bundle and source snapshot coverage already exist in
  [authoring tests](../backend/apps/core/tests/test_content_authoring.py:272).
  Native attachment tests explicitly include exact-Workspace and sibling denial
  ([tests](../backend/apps/core/tests/test_content_authoring.py:568)).
- The real repository journey creates a Git-native document through the UI,
  saves/reopens it and drives the canonical authoring endpoint
  ([journey](../frontend/e2e/repository-live-journey.ts:20)). Its existence does not
  prove native enrollment, key authoring or publication lifecycle coverage.
- Diagram source is Markdown fenced content, not a separate legacy-only diagram
  creation entity ([parser](../backend/apps/core/diagram_exports.py:223)). No
  independent native diagram-authoring implementation gap was established here.
  Exercise a fence authored in a new Git document through live export and signed
  publication; existing migrated-diagram tests are useful preservation evidence
  ([tests](../backend/apps/core/tests/test_diagram_publication_migration.py:53)).
- Native evidence permits the absence of a legacy document in general; the
  optional row lookup and native attachment owner filter are explicit
  ([retention](../backend/apps/core/repository_publication_evidence.py:148),
  [attachments](../backend/apps/core/repository_publication_evidence.py:205)).
  Existing backend evidence/packaging and portal semantics must be reused rather
  than replaced because their UI coverage is incomplete.
- Entity links are independently allowed portable metadata
  ([profile](../backend/apps/core/content_profile.py:42)); the key-binding gap
  does not establish absence of entity-reference support.

## Boundaries

No code, schema, API contract, document, production host or retained data was
changed by this source audit. No tests were run by this researcher. Runtime
reproduction and candidate acceptance belong to the parent audit's concrete
next-step checklist. Existing sharing, MFA, independent approval, signature,
resource and file-integrity guards must remain unchanged.

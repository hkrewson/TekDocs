# Content-key block substitution migration

Continuation of #105/#106 from `d8f75b4`, explicitly including content-key block
substitution in the user's scope reply. The completed field-key slice remains
historical evidence; this continuation has its own validation and review.

Acceptance uses the agreed migration, document read/publication, browser and
upgrade/recovery interfaces:

- Migrate consumers and the reusable block dependency graph together, preserving
  binding identities, exact source revisions, authored expressions and nested
  field/content keys. Content keys retain their existing current-revision
  semantics; ordinary pinned placements retain their selected revisions.
- Git-authoritative reads, current editable exports and publications use accepted, current Git block
  content, with no fallback to retained SQL Markdown. Keep permission and exact
  Workspace boundaries, limits, cycle checks and explicit unavailable states.
- New publications retain independently verifiable frozen substitution proof.
  Existing signed publications, PDFs and all managed-file versions remain exact
  through subsequent Git edits, withdrawal, authority rollback and recovery.
- Reject incomplete dependency handoff, stale previews/indexes, missing or
  denied sources, malformed/inline substitution, cycles and limit violations
  without partial authority, Git, SQL or artifact changes. Serialize writers
  against authority transitions.
- Keep API contracts, tests, architecture decision, roadmap, development notes,
  Wiki draft and known-risk disposition aligned. Complete both required source
  review axes and local Docker validation before the authorized direct-main push;
  bind required hosted upgrade/recovery receipts to the tested source.

Use the existing `tekdocs` Compose project and isolated test database only.
Independent fresh/upgrade/encrypted recovery environments remain hosted-only.
General cross-Workspace content-key reuse, client delivery and diagrams remain
outside this continuation. Version stays 0.9.16; no release, production change or
Wiki publication is authorized here.

Status: implementation and both source-review axes are complete. All 65 focused
Docker cases and three real browser journeys plus server-side custody/rollback
verification passed. The final combined migration/key/read/evidence regression
passed all 496 cases. Exact-source hosted gates remain pending.
The [source review](../releases/content-key-source-review.md)
records reproduced corrections and retracted candidates. No content-key runtime
completion or production acceptance is claimed.

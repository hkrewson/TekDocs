# Legacy document copy during 0.9.6

This is a bounded, operator-directed **copy** from PostgreSQL-authored
documents to the exact workspace's managed local Git repository. It does not
promote Git to document read or write authority. The legacy editor, revisions,
review workflow and publications remain authoritative throughout 0.9.6.
Run these commands from the TekDocs checkout using the migration service. Do
not run Git commands against the managed repository or edit its files directly.

## Before a copy

1. Work on a controlled database and repository copy first. Preserve a tested,
   encrypted recovery point containing PostgreSQL, managed files and workspace
   repositories before any production import. A database-only backup is not a
   complete recovery point for an accepted Git copy.
2. Verify the target workspace repository is healthy and its accepted and
   indexed commits agree. Use the exact `Workspace` UUID, not a tenant or
   organization UUID.
3. Inventory that workspace twice and compare the sorted JSON. Keep the
   inventory as operator evidence; it contains IDs, counts and reason codes,
   not document bodies.

```sh
docker compose run --rm migrate python manage.py inventory_document_migration --workspace <workspace-uuid>
```

An inventory `simple_candidate` is only a shape classification. It is not
approval to import or to switch authority. A deferred document stays in the
legacy store; do not hand-edit its repository files to bypass a reason code.
Import referenced source documents before targets that reuse their fragments.

## Preview and copy one document

```sh
docker compose run --rm migrate python manage.py preview_document_migration --workspace <workspace-uuid> --document <document-uuid>
docker compose run --rm migrate python manage.py import_document_migration --workspace <workspace-uuid> --document <document-uuid> --base-commit <preview-base-commit> --plan-sha256 <preview-plan-sha256> --actor <tenant-operator-uuid> --apply
```

Review the preview's `eligible`, `blockers`, file paths and SHA-256 digests,
source revision IDs, referenced fragments, attachment and key counts. The
preview reveals no body text. The import must use that exact base commit and
plan hash; if either source or repository changes, preview again. Record the
import response and accepted commit. `imported` or `already_present` with
`indexed: true` means the copy was verified, **not** promoted.

`index_pending`, `verification_pending`, `source_changed` and `blocked` require
investigation. Re-run the same import only when its preview is still valid to
complete interrupted indexing; it must not create a second copy commit. Do
not treat one of these states as successful handoff. The migration-status API
reports `content_copy_state`, `read_projection_state` and explicit
`handoff_blockers` for authorized staff. An `in_sync` copy can still have
repository-read, repository-write and publication blockers. Status re-verifies
the retained bytes of all active ordinary document attachments before calling
a copy `in_sync`; a missing or altered file reports `diverged` and does not
run the repository read comparison. It also re-reads each copied Markdown file
from the accepted Git revision and requires exact exported source bytes; an
unavailable or changed Git file likewise reports `diverged`. Repairing the
exact retained bytes can restore the shadow match, but does not promote
repository authority.

If a reviewed document is blocked by
`review_workflow_parity_not_verified`, do not edit its digest or review fields
directly. In Documentation, request a fresh review from the current document's
Ownership and review panel, have the assigned reviewer inspect the read-only
Git-backed content and record an approval, then recheck migration status and
the handoff preview. A new review pins the indexed Git composition's digest;
the prior decision remains in the audit history. If a current review cannot be
completed, leave the document PostgreSQL-authoritative.

## Explicit authority handoff

The operator handoff is a separate, per-document step. The migration-status
response sets `cutover_ready` only when the indexed copy and rendered read
projection match and no unsupported template, review-content digest,
publication, attachment-storage or other parity blocker is present. PostgreSQL
review schedules and workflow records remain operational authority; retained
review decisions must still match the canonical composed-content digest.
Retained primary-file
chains remain PostgreSQL-owned and are eligible when every version passes
ownership, chain, scan and byte-integrity checks; portable bundles include the
complete verified chain. A matching copy by itself is not sufficient.

Preview first, then use the exact Workspace, Document and active installation
member UUIDs shown by the operator inventory. The command does not write Git; it
changes PostgreSQL's durable authority state and appends an audit event. Owned
fragments transition with the document, and a fragment shared with a remaining
legacy-owned document prevents the handoff.

```sh
docker compose run --rm migrate python manage.py transition_document_authority --workspace <workspace-uuid> --document <document-uuid> --actor <operator-uuid> --authority repository
docker compose run --rm migrate python manage.py transition_document_authority --workspace <workspace-uuid> --document <document-uuid> --actor <operator-uuid> --authority repository --apply
```

The first command is a read-only readiness preview. For rollback, request
`--authority legacy` and review its blockers before adding `--apply`. Rollback
is refused if Git content no longer matches the PostgreSQL projection; reconcile
the content explicitly rather than discarding either side. Authority changes
are atomic and do not rewrite repository history.

While the first-wave handoff is active, PostgreSQL review workflow records stay
available and their content digest is computed from the indexed Git composition.
Portable document exports now render the accepted, indexed Git composition and
record its source path, commit, and content digest in the bundle manifest.
Selected and Markdown-referenced managed files are still verified against their
retained, scanned PostgreSQL attachment records. Portable bundle exports also
include the complete validated primary-file version chain and its selected
current version; other export formats do not duplicate those private files.
The legacy document STATIC publication endpoint, preflight and topic conversion remain deliberately
rejected for Git-authoritative documents; repository publication has a separate
evidence/review/package workflow and must be used instead of signing stale
PostgreSQL placements.

## Roll back an unchanged copy

```sh
docker compose run --rm migrate python manage.py rollback_document_migration --workspace <workspace-uuid> --document <document-uuid> --expected-commit <current-accepted-commit> --actor <tenant-operator-uuid> --apply
```

Rollback is a new audited Git commit that removes only unchanged files copied
for this document. It does not erase Git history, legacy revisions, attachments
or publications. Roll back a dependent target before its reused source.
Rollback refuses changed files, a stale accepted commit, or external incoming
links/includes. If refused, stop and reconcile deliberately; never reset or
rewrite managed Git history to force removal.

## Supported first wave and deliberate deferrals

The first wave handles ordered, live, shared owned sections, bounded nested
sections, supported same-workspace live/pinned leaf reuse, valid structured
topics, portable taxonomy selections, neutral outgoing same-workspace entity
mentions, ordinary attachment references and reader-scoped field-key
bindings. The importer preserves stable document and block IDs. It never
copies managed-file bytes or sensitive key values into Git.

Templates, template enrollments, publication-bearing documents,
cross-workspace reuse, pinned owned sections, non-leaf reuse,
content-expanding keys, ambiguous or unsupported relationships, and invalid
or archived records remain explicitly deferred. File/publication parity and
repository-inclusive recovery are 0.9.7 work. Retiring legacy writes or
promoting a document requires a separate, explicit authority transition after
read, write, review-content digest, template, key, attachment and publication parity; 0.9.6
does not provide that transition.

## Release rehearsal

`make test-document-migration-inventory` runs the PostgreSQL migration and
forced-RLS tests. `make document-migration-upgrade-rehearsal` creates synthetic
documents on 0.8.46, upgrades the preserved database, proves the original IDs
and revisions remain, and compares first-wave copy, retry and rollback with a
fresh installation. Both rehearsals use isolated test resources.

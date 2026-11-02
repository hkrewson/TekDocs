# Remaining #105/#106 migration audit

The maintainer authorized auditing and closing remaining migration gaps, starting
with cross-Workspace reuse. This ledger separates implemented closures, valid
legacy shapes still under investigation and intentional fail-closed prerequisites.
It must not be read as completed 1.0 acceptance.

## Cross-Workspace continuation

The [current slice](cross-workspace-reuse-migration.md) closes ordinary MSP library
reuse, client-listing primary reuse and unenrolled reuse of template blocks.
It includes mixed provenance and distinct pinned occurrences, reviewed pre-Git
revision archives, source dependencies, client-owned keys and retained publication
history. [Development evidence](../releases/cross-workspace-reuse-migration-notes.md)
records local reproductions and remaining validation gates.

## Additional valid shapes to close

| Shape | Audit evidence | Status |
| --- | --- | --- |
| Same-Workspace pin predating represented Git history | `test_repeated_shared_block_migration` deliberately reproduces the prerequisite; foreign archive support does not yet select local archives | Open implementation gap |
| Reusing a same-Workspace source Block that has children | Legacy resolution uses the Block body; `_linked_historical_leaf` / `_existing_references` reject source includes | Open body-only selection gap |
| Consumer-owned children under a reused placement | Legacy placement tree permits it; `owned_placement_tree` currently rejects `cross_document_nested_reference` | Open structural projection gap |
| Incoming record relationships and non-neutral outgoing relationships | Existing mapping rejects every incoming/non-REFERENCES/metadata-bearing edge although entity identities remain retained | Open semantic audit; do not invent neutral mentions |
| Removed, archived owned blocks | Normal removal archives the Block/revisions, while inventory's unplaced-owned query also sees archived rows | Reproduction and closure pending |
| Parameterized foreign reusable bodies | Legacy field/content keys resolve through the consuming document; current foreign fragment profile requires independent text | Reproduction and scope-preserving design pending |

These entries remain open until their own implementation, positive/negative tests,
signed/file preservation, rollback/recovery and review agree. No original signed
record or PDF may be rewritten to make a shape fit.

## Prerequisites that remain fail closed

- Missing, corrupt or unscanned file bytes; broken version chains; mismatched
  immutable revisions or signatures; unavailable/drifting Git custody.
- Foreign tenants, sibling-client sources, revoked/unapproved sharing, invalid
  placement ownership, cycles and ambiguous owned identity graphs.
- Resource limits, archived-document lifecycle and topic/taxonomy mappings that
  require an explicit operator decision. Do not truncate, unarchive or invent
  business metadata automatically.
- Foreign source-owned attachment URLs are not portable consumer attachments:
  the legacy renderer also resolves files from the exact consuming document.
  Keep those unavailable rather than acquiring another Workspace's files.

Repository initialization and a current index are explicit operational
prerequisites. An inventory candidate is not permission to import or promote.
Production inspection, deployment, live-data migration and public Wiki publication
need their own authorization.

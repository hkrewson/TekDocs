# Content-key migration development notes

Unreleased #105/#106 continuation; version remains 0.9.16. The maintainer explicitly
included content-key block substitution after the completed field-key slice.
The [slice record](../migrations/content-key-publication-migration.md) tracks
acceptance, source review and validation. No release or production change is claimed.

Documents can move with the reusable block sources selected by their content
keys, including nested substitutions and scalar keys. Sources and consumers must
transition and roll back as a complete live dependency group. Existing pinned
placements keep their selected revisions; content keys keep current-body behavior.
Bindings keep their identities and remain read-only until database authority
is restored.

Live Git readers expand permitted accepted source bytes. New STATIC v10
publications freeze those bytes with Git proof, nested resolutions, record cards,
owned managed files and PDFs. Existing signed publications, PDFs and complete file
version chains stay intact. Missing, stale or denied dependencies block publication
without partial history, and unavailable reads show explicit markers.
Current editable exports also use accepted Git substitution bytes. Their portable
v4 manifest records Git content provenance; older legacy/field-only v3 exports
retain their contract. The separate older repository-evidence format continues
to refuse content snapshots before creating evidence or retained files.

All three local real-browser journeys and server-side custody/rollback checks
passed, alongside 65 focused content cases and both source-review axes. The hosted
fresh/0.8.46 migration and independent encrypted-recovery checks passed against
runtime `781f1ad`, confirming the same graph, retained signed publications, PDFs
and file versions. Build, CodeQL and Extended validation all passed; the slice
record links their exact-source receipts. The final combined local migration,
key, read and evidence regression passed all 496 cases.
Local focused tests alone do not establish independent restore or production
acceptance. General cross-Workspace reuse, diagrams and client delivery remain
separate. Existing CSP/COEP/KaTeX allowances and open development-tool findings
retain their recorded ownership/expiry; this slice does not accept or renew them.

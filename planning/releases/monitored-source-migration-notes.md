# Monitored-source migration development notes

Unreleased #105/#106 continuation, version 0.9.16. The
[slice record](../migrations/monitored-source-publication-migration.md) owns
acceptance and validation status. Source review is clear and all five live
browser/server journeys passed. Local validation passed 656 combined Docker
cases, 34 final source/transport cases and 793 frontend cases. Exact-source hosted
receipts remain pending.

Supported monitored documents retain source settings, schedules and immutable
observation history when authored content moves to Git. Local revisions, signed
publications, PDFs and every file version keep their original custody. Missing
or invalid retained history blocks migration. URLs and observations remain
workflow records and do not enter authored Git frontmatter.

Web source remains available in the promoted reader. Checking creates retained
observations without changing content. Applying requires a current review of the
owned primary section and writes through the coordinated Git authoring boundary.
Changed source settings, authority, content or incomplete indexing refuse the
write. Local edits require manual integration in the repository editor; applying
does not overwrite them. A refused apply keeps the source panel and draft open. The review discloses live
reuse impact and retained pinned/signed content. A later unchanged check does
not hide an earlier source change that still needs review.

Rollback and re-promotion preserve source workflow state alongside retained
content and artifacts. Hosted upgrade and independent encrypted recovery compare
the synthetic cohort across fresh and 0.8.46 installations without contacting an
upstream server. Existing CSP/COEP/KaTeX dispositions and development/build-tool
findings retain their ownership and expiry; this slice renews no exception.

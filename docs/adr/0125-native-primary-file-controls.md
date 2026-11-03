# 0125: Primary-file controls for Git-native documents

Status: accepted; local browser, recovery and combined validation passed.
Exact-source hosted independent restore and supported upgrades remain required.

A newly authored Git document has no legacy Document row. Its primary-file
append, history and download services already retain immutable managed files
under an exact Workspace/content owner. The interface connects those services;
it creates no compatibility row, second content authority or new storage path.
Markdown remains canonical in Git; binary bytes and immutable version lineage
remain in the existing managed-file store and database records.

The file panel loads on explicit request and pages through descending versions.
First upload compares against an empty current pointer; replacement submits the
reviewed current entity ID. Every replacement requires explicit confirmation.
Conflicts or unconfirmed uploads retain the selected File in the browser and
require history refresh before retry. Refresh clears replacement confirmation;
a changed current version must be reviewed again. A version-count change during
paging refuses the inconsistent page and requires a fresh history read.

Uploading a file never saves or replaces an unfinished Markdown draft. File
selection and transfers register with the existing navigation guard. New
publication retention remains disabled while a file selection/transfer is
unfinished; retained publication decisions continue to act on their original
signed evidence. Download errors remain in the file panel instead of navigating
away from a draft. Downloads use the existing private, integrity-checked route,
require complete attachment responses, and preserve original filenames.

Authorization, scanning, exact-owner lookup, content checksums, immutable SQL
lineage and current-version compare-and-swap remain server responsibilities.
The interface handles denials and validates response lineage; disabled controls
are not authorization. No public/portal access to live primary files is added.
Client publications retain independent approval and exact-client delivery.

The shared history route also lists exact promoted legacy-owner versions instead
of misreporting their retained chain as empty. Both read and append require
repository authority for that owner; unpromoted or rolled-back shadows return
409. Exact tenant, Workspace, content and matching legacy-owner filters remain.
This corrects a read/authority adapter; it neither migrates nor rewrites records.
No schema, endpoint or payload shape changes; the existing 409 outcomes are
documented in OpenAPI. Recovery now carries three native
primary versions: one bound to the first staff publication, two bound to its
correction, and a third uploaded afterward. The fingerprint compares all live
versions and separately verifies original signed manifests, decision events,
PDFs and independently retained files. A later Git write must not change that
fingerprint. Damaged live bytes fail verification while intact signed copies
remain verifiable. Existing schema rollback safeguards remain unchanged.

Keys, templates, monitored-source configuration, automatic legacy migration,
primary-PDF viewing and the post-1.0 interface redesign remain separate work.

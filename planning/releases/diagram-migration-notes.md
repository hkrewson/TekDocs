# Diagram migration development notes

Unreleased #105/#106 continuation, version 0.9.16. The
[slice record](../migrations/diagram-publication-migration.md) owns acceptance and
validation status; this is not a release or production migration.

Supported diagram-bearing documents can migrate with their canonical Mermaid
source and verified signed history. Existing source revisions, signed SVG/PNG,
PDFs and managed-file versions stay intact. Current Git compositions, including
supported reused content, can publish internal STATIC v11 snapshots with frozen
source/render evidence and retained graphics. Downloads includes those SVG/PNG
files alongside retained attachments. Missing or corrupt custody blocks migration
and rollback; renderer or source failure blocks publication without partial files.

Local validation passed: 524 backend cases (two existing opt-in skips), three
additional cases, all 33 diagram cases, 781 frontend tests and four real-browser
journeys with server-side custody and rollback verification. Both source reviews
have zero remaining findings. Runtime `5b7a9314` passed complete Build, CodeQL
and Extended validation, including all sixteen database groups, 33 diagram cases,
89% backend coverage, fresh/0.8.46 migration and independent encrypted recovery.
The slice record links the exact-source receipts and retained-byte verification.
The bounded development slice is complete. The existing
CSP/COEP/KaTeX dispositions and development/build-tool findings retain their
ownership and expiry; this slice accepts or renews no exception.

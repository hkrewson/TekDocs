# Field-key and entity-reference migration development notes

Version remains 0.9.16. This is an unreleased #105/#106 continuation. Source
`6ce9519` passed Build, CodeQL and Extended validation, including fresh/0.8.46
migration, real browser/server acceptance and exact encrypted recovery. The
[slice record](../migrations/key-entity-publication-migration.md) binds receipts
and preserves prior failures and open follow-ups.

Supported internal documents can retain portable field bindings and typed links
to records in their own Workspace while moving to Git. The live reader shows
current permitted values. Publishing freezes those values, record cards and
managed-file versions in a signed snapshot with a retained PDF. Existing signed
publications and PDFs stay intact. Corrections create a new immutable snapshot.

The Keys panel is available on migrated documents. It reports the current Git
expressions and retained bindings, and can retry a failed read. Binding changes
remain available after rollback to legacy editing. Missing or denied references
block publication without changing history. Rollback and encrypted recovery
must preserve the expressions, binding identities, file versions and evidence.

Adding a client now preserves the current content index for existing repositories
when only portable manifests change. A previously stale index remains blocked.

Content-key block substitution, foreign record references, client delivery,
diagrams and live production migration remain separate. No dependency or header
risk allowance is renewed by this development slice. Existing CSP/COEP/KaTeX risk
ownership and expiry remain as recorded for 0.9.16; no new runtime dependency is
introduced. Hosted scans remain required for the exact pushed source.

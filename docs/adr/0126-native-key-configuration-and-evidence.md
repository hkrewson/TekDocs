# 0126: Native key configuration and frozen evidence

Status: accepted bounded scope; local validation complete; hosted validation pending. Date: 2026-11-03.

New Git documents own their `key_bindings` in validated frontmatter. The existing
protected authoring transaction saves the exact reviewed commit/blob and Markdown
with the declarations. It creates no legacy Document, Block or SQL key-binding
record. Existing legacy/promoted binding configuration stays read-only. A scoped
read endpoint supplies reauthorized target descriptors and a saved-source report;
it returns no resolved field values. Pending targets are reauthorized on reads.

Use the existing policy, field allowlist, sensitivity rules, inert scalar values,
cycle/depth/output limits and explicit unavailable states. Native content keys
select current accepted fragments in the same Workspace, without a new pin mode.
Nested keys resolve in the consuming document's binding and file-owner context.
Live reader, PDF and DOCX exports use the same expanded saved body. Those exports
remain live revisions, not signed STATIC publications.

The lazy Keys and references panel stages declarations, removals and URI insertion
in the normal draft. Save to Git commits them together. Denial, conflict, stale
source and navigation preserve drafts; source changes require explicit reload.
An unfinished binding name protects navigation and prevents snapshot retention.
The server remains the permission and source authority.

Native addressed evidence uses additive evidence v3. Retain exact root source,
normalized binding IDs, bounded fragment source/blob/commit proofs, field values,
entity cards, rendered HTML/PDF and independent managed files. Raw proof is
staff-only. Portal delivery exposes the separately approved rendered result.
Offline verification reconstructs frozen substitutions and checks root and
fragment identities without current records or Git. Older evidence and signed
publication contracts retain their bytes and verification rules. Existing
package/static contracts already bind the exact evidence digest and need no
new payload format; migration 0220 extends their validators for evidence v3.

The additive SQL validator checks source/index identity, binding/scope agreement
and snapshot shape. It does not duplicate Markdown/signature verification.
Rollback refuses any retained v3 evidence atomically and preserves FORCE RLS.
No existing records are rewritten. Independent recovery carries both current
retargeted bindings/source and earlier signed frozen values, PDFs and file
versions; a later unrelated Git write does not invalidate its fingerprint.

Automatic legacy migration, cross-Workspace native bindings, template enrollment,
monitored-source configuration and interface redesign remain outside this slice.
The six deferred migration gaps remain outside the clean-start 1.0 blockers.

New native content-key bindings accept native fragments only. Legacy Block-backed
fragments (including copied, promoted, rolled-back and archived sources) remain
in their existing workflow; their IDs cannot bypass legacy permissions through
a native binding. Existing documents and publications are not rewritten.

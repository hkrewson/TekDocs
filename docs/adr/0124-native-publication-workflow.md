# 0124: Native publication workflow and staff decisions

Status: accepted; local Docker runtime and browser/server acceptance passed.
Exact-source hosted upgrade and independent recovery remain required.

New managed Git documents need not have a legacy `Document`. Their client
publication chain already retains signed evidence, independent review, package
authorization, signed STATIC records, release and explicit client delivery.
Staff evidence previously had no publication decision. Creating compatibility
rows to unlock the older interface would give the clean-start flow a second
content authority and is excluded.

The editor uses the existing client services without bypassing any approval,
MFA, interactive-authentication, integrity or exact-Workspace gate. A read-only
workflow summary reports current state and actor-appropriate actions through
the central policy service. Summaries do not authorize subsequent mutations.
Every action revalidates its service boundary. A correction explicitly confirms
replacement of the current release. Rejected decisions remain immutable; a new
snapshot is needed to restart.

Staff publication records an append-only `RepositoryInternalPublicationEvent`
over existing signed evidence. The evidence signature continues to describe the
exact retained source and file/PDF bytes; the new decision does not relabel its
manifest as a client STATIC record or attest client approval. Publisher permission
and MFA govern staff publication; approval permission and MFA govern withdrawal.
The same maintainer may publish staff-only work. These events never create portal
authorization, client packages, client release or client delivery records.

Forced exact-Workspace RLS and SQL scope, lineage and immutability guards protect
the new table. Services and triggers serialize by Workspace/content, require the
active predecessor for correction, and permit withdrawal only for the current
release. Withdrawal never reactivates a superseded predecessor. Staff history
and verified PDFs remain available to authorized staff after withdrawal.

Retention optionally compares `expected_commit` inside the existing pinned-source
lock. The interface always supplies its reviewed loaded commit and blocks new
retention while the editor has unsaved changes. This additive API field preserves
older callers while preventing a new interface action from silently freezing
unreviewed changes. Integrity failures never fall back to live content.

Migration 0219 creates only the new decision table and guards. It writes no
existing document, evidence or publication. Empty-schema reversal/reapplication
is supported; reversal with recorded decisions refuses before dropping anything.
Normal database/media/repository backup retains the existing evidence files and
new decisions. Independent recovery remains a candidate-matched hosted gate.

Primary-file controls, keys, templates, monitoring configuration, automatic legacy
migration and the post-1.0 interface redesign remain separate work.

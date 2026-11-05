# 0127: Native template enrollment and retained source proof

Status: accepted; implemented with local validation complete. Date: 2026-11-03.

New MSP Git documents can be explicitly offered as templates through the saved
document editor. Selected immediate native text fragments become approved library
sections. Git owns the document, portable declarations and section bytes. The
PostgreSQL control plane owns the approved source identity, immutable definition
revisions and each client's enrollment map. No legacy Document or Block is created.

The client Templates tab offers independent copy, live and pinned behavior for
each section. The introduction is always a destination-owned copy. Copied sections
get independent fragment identities; foreign references retain their approved
source Workspace and exact enrollment revision. The library loader exposes only
the selected approved leaf, never arbitrary source repository content. Existing
policy, exact Workspace RLS and legacy-shadow exclusion apply at every boundary.
Nested source graphs and source-owned keys, entity references and files require a
separate disclosure/copy contract and are not silently inherited.

Review binds the destination commit/blob, applied enrollment revision and offered
source revision. Source or destination changes invalidate stale submissions.
Copies remain independent by default; replacing local text is an explicit review
choice. Removed borrowed sections require explicit preservation as local text.
Detach copies the currently selected bytes. The protected authoring path cannot
forge or rewrite an enrollment include map. Coordinated Git/database transactions
prevent partial enrollment and stranded accepted refs after late failures.

After validating the exact enrollment shape, unavailable source custody produces
an empty unavailable projection for affected documents. Forged grants remain hard
errors. Discovery, graph and reader boundaries refresh before returning cached
composition. Independent copies do not require source availability or a source Git
publication lock; revoked foreign bytes cannot survive in search or graph output.

Native publication evidence v4 retains the exact template definition, selected
source bytes, Git object proof, approved revision and consuming include identity.
Its dependency envelope is versioned separately. Live proofs retain the selected
accepted source head; pins retain their immutable revision's commit. An unrelated
source commit need not create an identical template definition. Verification uses
retained bytes and the enclosing signature, without current source Git or an
enrollment lookup. Frozen keys, entity cards, signed PDFs and independently owned
primary-file versions keep their existing custody rules. Earlier evidence formats
keep their original verification constraints.

The SQL evidence validator checks the exact enrollment, placement, source revision
and selected bytes at insertion. It complements Python's Markdown/Git/signature
verification. Native revisions and publication evidence are immutable. Schema
rollback refuses to discard retained enrollments or v4 evidence; empty-schema
rollback remains supported. Recovery includes native source registries, revisions,
enrollments, current repositories, independently retained files and signed output.

This does not migrate existing documents, deploy an application, change the
published 0.9.18 checkpoint, revive the six deferred migration blockers or begin
the post-1.0 interface redesign. Validation and disposition are tracked in
[the slice acceptance record](../../planning/git-native-templates.md).

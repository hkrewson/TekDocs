# ADR 0123: Scoped cross-Workspace library custody

Status: accepted for the maintainer-authorized #105/#106 migration continuation.
Baseline: `cac36757`, development after published 0.9.18.

## Decision

Classify the provenance of each use separately from its source's type. A shared
Block from a template can be reused without enrolling the consuming document.
Enrolled occurrences keep their immutable template-definition certificate;
unenrolled occurrences name the source Document and selected Block revision.

Unenrolled foreign includes add `library_source` alongside `library_workspace`.
A pinned include also names its immutable Block revision in `library_revision`;
live includes have no revision discriminator. Template includes retain the prior
Workspace/template-revision pair. A normal Django constraint distinguishes these
forms. No consumer copy of an MSP source fragment becomes authoritative.

The retained placement must authorize every read. Existing Document/Block library
opt-ins permit independent shared blocks; an active client listing permits its
existing primary-block reuse. The source and consumer must belong to the same
tenant, and another client's source remains unavailable. A foreign include reads
only its selected Block body, even when the source fragment has owned children.
Source keys, entity links and files cannot silently acquire a client's namespace.

Reviewed history retention writes immutable `shared-snapshots/<revision>/...content`
objects from checksum-verified Block revisions. It never temporarily replaces the
current source with older bodies. A stable archive title describes retained body
custody rather than inventing historical Block-name revisions. Template sources
also retain their existing complete template-definition archives. Source
repositories, immutable database revisions and managed file storage remain part
of one recovery set.

One coordinator obtains sorted repository leases, locks owners, verifies policy
and MFA in every Workspace and binds the exact reviewed source/consumer group.
Single-document paths enforce the same library/template MFA gate before Git
access and again after the owner and owned Blocks are locked. The scoped
participant classifier returns only a boolean; ordinary documents retain their
prior service-level authorization behavior. Temporary scope binding restores all
six scope/principal settings after success or failure.
A boolean-only SQL check detects omitted live consumers and content-key edges,
including inaccessible clients, without returning their identities. Promotion
stages root authority atomically; rollback projects all owned bodies before any
consumer parity check. Foreign pins require their source to remain repository
backed while the consumer is promoted. Preview and every authority entry point
check that directional invariant. A deferred database guard serializes source
rollback and consumer promotion on the stable source Blocks and checks the exact
source/consumer Workspace authority rows; consumer-first rollback remains valid.

Publication refreshes derived foreign-LIVE composition under sorted source and
consumer pins. Discovery covers all retained foreign includes in the refreshed
repository, including owned fragments without imported roots. Required source IDs
are checked again after lock acquisition; drift fails closed without acquiring
new locks out of order. Publication does not require a preceding content read.

## Signed source proof

New unenrolled-library publications use a v13 envelope and Git-dependency v3
proof. The signed `library_format` names the unchanged inner v7-v12 certificate.
Ordinary records bind `library_source`, `block_revision`, `block_checksum`, exact
Git object/blob/path, Workspace and body-only selection. They never claim a
template revision. Nested repetition, diagrams and client-owned key/entity
certificates keep their existing validators. Original manifest bytes remain the
signature input; normalization is a validation-only view.

Normal reversible migrations 0214-0218 validate the discriminated include,
per-occurrence source proof, complete closure and read/write isolation. Historical
publication formats cannot admit the new ordinary-source fields. Retained v13
rows survive reversing/reapplying the publication guard; the older guard refuses
new v13 insertions. Authority rollback uses the current application/schema.
Deploying an older application that cannot understand v13 is not an authority
rollback; full recovery must restore a compatible application and recovery set.

## Isolation correction

The prior foreign Document visibility rule also made all its placements visible.
That is appropriate for an explicitly shared template blueprint or client listing,
but exposed unmarked sections of an ordinary library document. A dedicated scoped
projection now preserves those distinctions. Foreign placement/Block SELECT
policies are separate from owner-scoped writes; foreign reads grant no update or
delete access. Approved reuse uses the existing placement INSERT trigger's source
lock and rechecks scope and authority while that lock is held. Ordinary legacy
writers check the approved source-root authority too, because client RLS hides
foreign fragment authority rows; they cannot accept Git-owned revision caches. Approved template copies retain their prior blueprint visibility.

## Verification and limits

Public service/API regressions cover ordinary sharing, client listings, template
sources without enrollment, mixed enrolled/unenrolled occurrences, distinct pins,
audiences, client keys, source dependencies, stale plans, denied operators,
missing storage, failure rollback and unchanged signatures/PDF/file versions.
The browser, hosted fresh/0.8.46 upgrade and independent encrypted restore fixtures
exercise both repositories and archived pins. Source review and exact-source
delivery evidence are recorded in the continuation's notes.

This decision does not bypass corrupt custody, invalid scope, mapping prerequisites
or resource limits. The [remaining-gap audit](../../planning/migrations/remaining-migration-audit.md)
tracks further legitimate shapes separately; it is not a declaration that 1.0
migration coverage is complete.

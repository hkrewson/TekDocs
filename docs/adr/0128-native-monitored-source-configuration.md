# 0128: Native monitored-source configuration

Status: proposed for the 1.0 clean-start candidate.

## Decision

Keep monitored-source settings and immutable observations in PostgreSQL while
allowing the source owner to be either a legacy document or an exact Git-native
repository document. The two owner shapes are exclusive and immutable. Native
review fingerprints bind settings state, retained observation, accepted commit
and source blob. Reviewed apply writes the document through the coordinated Git
authoring boundary and advances the SQL applied pointer only after the indexed
result is verified.

The existing approved-egress controls, policy service, RLS scope and retained
observation format remain authoritative. Native publication evidence is refused
while a changed observation is unapplied. Source settings and observations are
not written into Markdown or copied into a signed publication.

## Consequences

Git-only documents gain the existing check/review/apply workflow without a shadow
legacy document. Existing legacy and promoted workflows retain their identities
and behavior. Recovery must retain the repository, source owner, observations and
applied pointer together. Migration rollback is refused after native source state
exists because discarding that workflow history would be lossy.

Automatic migration of legacy monitored settings and forced merging of local
edits remain excluded.

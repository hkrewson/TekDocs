# ADR 0097: Structured topics and publication preflight

Status: accepted for issues #30 and #31.

## Decision

TekDocs keeps Markdown canonical. A structured document declares one versioned topic type: unstructured, policy, procedure, guide, troubleshooting, reference, system overview, or change runbook. The catalog provides complete starter Markdown so the author chooses one compact template control and immediately edits the resulting structure; it is not merely a classification field. Required section identity comes from ordinary level-two Markdown heading text. No hidden comments or editor-only syntax appear in authored content. The immutable block revision records the topic type and schema version, so older revisions are never reinterpreted or rewritten.

Conversion is explicit and previewed. It removes obsolete TekDocs section comments, retains authored headings and content, places retained content in the first guided section, and adds the remaining required sections. Templates carry the topic contract into enrolled documents. Publication and portable-export manifests retain the topic type and schema version.

One preflight service owns stable machine codes and severity. It checks the exact audience-resolved composition before a STATIC publication and normalizes documentation-map baseline checks through the same service boundary. Preview is read-only. Publication runs the check again after locking the document composition and creates no publication, signature, artifact, event, notification, or portal projection when a blocker exists. Warnings remain reviewable but do not bypass blockers.

Telemetry contains only scope class and finding codes. It does not log authored content, resolved values, customer identifiers, or inaccessible dependency details.

## Compatibility

Existing documents and historical revisions default to unstructured schema version 1. New manifest fields are additive. Later schema versions must remain parseable and may not rewrite historical revisions.

## Consequences

Authors receive guided structure without adopting DITA XML, hidden comments, or a schema designer. Extra headings remain allowed. Missing or duplicate required headings block publication; empty or out-of-order sections warn unless a later versioned policy explicitly changes the maintained severity catalog.

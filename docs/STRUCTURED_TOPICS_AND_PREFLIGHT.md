# Structured topics and publication preflight

Issues #30 and #31 add guided MSP authoring and a deterministic release check while preserving canonical Markdown.

The topic schema catalog is available from `GET /api/v1/documents/topic-schemas`. Document create and update payloads accept `topic_type`; document and immutable revision responses include `topic_type` and `topic_schema_version`. Existing documents remain `unstructured`. `POST .../topic-conversion` previews by default and applies only with `apply: true` plus the exact current `base_revision_id`.

`GET .../preflight?audience=msp_internal|client_visible` returns `tekdocs-preflight/v1`, the exact composition digest, deterministic severity counts, and ordered findings. Every finding has a stable code, maintained severity, summary, remediation, edit target, and optional semantic section and line. Checks cover semantic sections, ownership and review state, keys, record links, files, remote observations, template enrollment state, and diagram rendering and accessibility. The catalog endpoint documents all current codes.

STATIC publication reruns preflight after acquiring the composition lock. A blocker returns a publication conflict before retained state is created. Documentation-map preview and baseline creation use the same preflight service boundary; baseline creation reruns its checks under the map revision lock.

The publication and portable export manifests add optional `topic_type` and `topic_schema_version` fields. Publication manifests also retain the preflight contract version, checked composition digest, and severity counts without copying finding content into the signed artifact.

The stable semantic convention is:

```markdown
<!-- tekdocs:section validation -->
## Validation

Describe how the technician proves the result.
```

Only the marker provides semantic identity. The heading remains presentation text and may be renamed. Extra unmarked sections are allowed. DITA XML and installation-defined topic schemas remain out of scope.

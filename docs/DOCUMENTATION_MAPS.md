# Documentation maps and handoff baselines

Documentation maps are versioned tables of contents for operational material. A map can include a live document, an exact document revision, an immutable STATIC publication, a subordinate map, or a safe external HTTPS reference. Entries have explicit sibling order and optional parent entries.

## Guarantees

- Every save appends a map revision; prior revisions and entries cannot be changed or deleted.
- Updates require the current revision identifier and reject stale editors with HTTP 409.
- Every target is checked against the map Workspace. Cross-tenant and cross-organization references are rejected in both application logic and database triggers.
- Client-visible maps may contain only approved, current client-visible publications and approved client-visible subordinate maps.
- Cycles, duplicate sibling targets, unavailable content, withdrawn publications, archived maps, and unowned or unreviewed content are reported before export.
- Baselines retain the exact map revision, ordering, dependency identifiers and digests, actor, timestamp, generated files, and SHA-256 checksums.
- ZIP output is deterministic and contains `manifest.json`, `index.md`, `index.html`, source Markdown and HTML, retained artifacts, plus requested PDF or DOCX renderings.

## API outline

The same operations are available at the MSP scope and under an organization Workspace:

- `GET|POST /api/v1/documentation-maps`
- `GET|PUT|DELETE /api/v1/documentation-maps/{map_id}`
- `GET /api/v1/documentation-maps/choices`
- `POST /api/v1/documentation-maps/{map_id}/review`
- `GET /api/v1/documentation-maps/{map_id}/preview`
- `POST /api/v1/documentation-maps/{map_id}/baselines`
- `GET /api/v1/documentation-maps/{map_id}/baselines/{baseline_id}/download`

Organization routes insert `/workspaces/organizations/{organization_id}` before `/documentation-maps`. Client portal members can list and download only current approved baselines through `/api/v1/portal/documentation-maps`.

## Limits and exclusions

A map accepts at most 250 direct entries. A retained baseline is capped at 500 resolved entries per map and 100 MiB. External references must use public HTTPS URLs and are recorded, never fetched. DITA XML import is not part of this capability.

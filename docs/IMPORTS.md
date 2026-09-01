# Imports and migration

Use **Integrations → Imports** inside the Workspace that will own the records. An import never aggregates clients and cannot create a relationship to a sibling Workspace.

## Supported input

- TekDocs bundle version 1 (`manifest.json` plus UTF-8 `records.jsonl`)
- TekDocs CSV templates
- ITFlow, IT Glue, and Hudu CSV exports mapped to a selected TekDocs record family
- Organizations, people, sites, locations, vendors, products, models, assets, software licenses, networks, documents, document metadata, and credential references without secret values

Download the template for the destination record family from the Imports screen. Preserve a source identifier in `external_key`; reruns use it to update or skip the same record. Source exports vary by version, so rename columns to the template headers when an exporter does not provide a recognized alias and remove unsupported columns after reviewing them. TekDocs rejects rather than silently discards extra columns. Do not combine record families in one CSV.

The native bundle manifest is:

```json
{"format":"tekdocs-import","version":1}
```

Each line of `records.jsonl` has this shape:

```json
{"record_type":"sites","external_key":"itflow:site:42","data":{"name":"Main office","city":"Ankeny"}}
```

## Safe workflow

1. Select the source format and CSV record family, or select a native bundle.
2. Upload the file and choose **Preview import**. No domain record is changed.
3. Review every row and download the result report if the source needs correction.
4. Confirm any proposed exact match with **Use existing record**. TekDocs never auto-merges fuzzy matches.
5. Resolve all conflicts and rejected rows, then choose **Apply import**. Apply is one transaction: all accepted rows succeed or none do.
6. Rerun the same corrected source safely. Stable external keys produce updates or unchanged rows rather than duplicates.

Cancel discards staged values. Unapplied previews expire after 24 hours. Applied and cancelled batches retain only value-safe metadata and reports.

## Source mapping notes

ITFlow `client`, `contact`, `location`, `vendor`, `asset`, `software`, `network`, and `document` identifiers belong in `external_key`. Map client/contact names and addresses to the corresponding TekDocs template fields. For IT Glue and Hudu, export one object family at a time and map its durable object ID to `external_key`; use the native organization/site/asset fields, and convert safe text documentation to Markdown before upload. Where an export shape changes, the downloaded TekDocs template is authoritative.

Model and asset imports must reference existing exact entities where their template requests an entity ID. License relationships may use an asset external key created in the same batch. Credential references accept only 1Password links and metadata—never usernames, passwords, recovery codes, private notes, API keys, or tokens.

## Rejection and limits

TekDocs rejects malformed UTF-8, unexpected headers or bundle members, path traversal, compressed expansion abuse, formula-leading cells, secret-shaped fields, duplicate external keys, unknown record types, excessive rows or fields, and cross-Workspace references. Unsupported attachments and proprietary editor payloads are explicit rejections; submit safe files separately through the normal scanned attachment intake.

The current limits are 25 MiB uploaded, 100 MiB expanded, 64 archive members, 10,000 rows, 80 columns, 64 KiB per field, and 60 seconds for preview or apply processing. Split larger migrations into independently reviewable batches.

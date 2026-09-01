# ADR 0095: Safe import reconciliation

Status: accepted
Date: 2026-09-01

## Decision

TekDocs imports data through an explicit parse, normalize, validate, match, preview, apply, and report pipeline. The browser uploads either a version-1 native bundle or an allowlisted CSV family. Preview creates only short-lived staging rows and external-key metadata; it does not write domain records. Apply locks one preview and performs all accepted domain changes and external-key updates in one database transaction.

Every row has one public disposition: `create`, `update`, `unchanged`, `conflict`, or `rejected`. A stable source-system, record-type, and external-key tuple is the idempotency authority. An exact candidate can be proposed, but no name or fuzzy match is applied until an operator confirms that exact entity. Duplicate external keys, ambiguous records, unsupported relationships, and cross-Workspace references fail closed.

All records are created through the existing domain services. Imported documentation remains canonical Markdown and therefore uses the normal reference, revision, rendering, and publication boundaries. Credential imports accept 1Password references only; plaintext credentials and secret-shaped fields are rejected. Formulas, malformed UTF-8, unsafe archives, unknown bundle members, oversized fields, and excessive expansion are rejected before domain writes.

## Bundle and staging contract

A native ZIP contains exact root members `manifest.json` and `records.jsonl`. The manifest is `{"format":"tekdocs-import","version":1}`. Each JSON line names `record_type`, `external_key`, and `data`. CSV uses the downloaded exact template for one selected record family. Source formats retain distinct provenance labels for TekDocs, ITFlow, IT Glue, and Hudu; unstable vendor exports are adapted through documented column mappings rather than private APIs or scraping.

Raw input is never stored. Normalized staging expires after 24 hours and is erased immediately after apply or cancel. Retained batch metadata contains the source digest, filename, counts, safe reason codes, and timestamps. Reports escape spreadsheet-formula prefixes and never include source values or secrets.

## Ownership and failure behavior

One batch is bound immutably to a tenant and exact Workspace. Database triggers and forced RLS reject cross-tenant, sibling-client, wrong-Workspace mapping, and local-entity substitution. Apply is synchronous and bounded; an expected validation failure leaves the preview available for correction or cancellation, while a transaction failure rolls back every domain change and mapping. An applied batch is immutable and a repeated bundle reconciles through the retained external keys.

Attachments and proprietary editor payloads are not silently flattened. Version 1 rejects unsupported attachment records; operators import accepted Markdown and submit attachments separately through the ordinary scanned attachment workflow.

## Consequences

Migration becomes inspectable and repeatable without creating a second write authority. The size and row ceilings favor reviewable batches over unattended bulk ETL. Live synchronization, credential-value custody, automatic fuzzy merge, proprietary-editor fidelity, and provider-private API clients remain outside this contract.

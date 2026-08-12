# ADR 0062: Read-only integration runtime and sanitized Git export

Date: 2026-08-12

Status: Accepted for `0.6.4`–`0.6.8`

## Context

An MSP connector crosses three sensitive boundaries at once: a long-lived provider credential, server-side network egress, and remote data that may be incomplete or hostile. Treating a remote system as canonical could overwrite exact-client TekDocs records or infer deletion from a partial response. Exporting TekDocs content to Git can likewise create an uncontrolled copy of credentials, attachments, audit evidence, or provider payloads.

## Decision

- Providers implement a small registry contract. NetBox is the first adapter and is read-only. Its connection belongs to one explicit Workspace; no aggregate client sync or ordinary Networks “link” UI exists.
- API tokens enter only a recent MFA-authenticated session boundary, are envelope-encrypted with tenant/connection/generation associated data, and are decrypted only inside the worker immediately before use. Lists, audits, logs, jobs, conflicts, exports, and browser responses do not contain the value.
- Provider egress requires a public DNS HTTPS origin on port 443, pins the reviewed address while preserving certificate hostname verification, follows no redirects, and bounds time and response bytes. The adapter validates pagination remains on the same origin.
- Each provider page is a durable idempotent job with bounded cursor, lease, backoff, and attempts. The dispatcher submits bounded exact-Workspace job identities to separate worker tasks rather than performing provider I/O in its scheduling loop. Raw remote objects are hashed and discarded at the adapter boundary; retained observations contain only type, ID, fingerprint, and time.
- Reconciliation is explicit. Differences never write back to the provider or mutate a TekDocs domain record automatically. “Accept remote” acknowledges only a linked external fingerprint; unmatched records remain unmatched until a separately authorized mapping workflow exists.
- Provider operational history uses fixed event codes and numeric metrics with 30-day retention. It is deliberately separate from process logs and does not claim to resolve the process-wide structured-logging risk.
- Git output is a retained deterministic ZIP suitable for unpacking into a working tree. It contains selected canonical Markdown and STATIC manifests plus a selection manifest. Credential and live-attachment links, attachment content, secrets, audit data, provider payloads, and editor HTML are excluded; a STATIC manifest with credential-reference metadata is rejected as a whole. Admitted signed manifests retain their evidence metadata unchanged so their digest/signature contract is not falsified. This release neither creates commits nor configures/pushes a remote.

## Consequences

TekDocs can reconcile a bounded NetBox projection without becoming a partial NetBox clone or giving a connector implicit write authority. An installation administrator who controls both the database and deployment wrapping key can still decrypt provider credentials. Job scale, adversarial proxy/DNS behavior, exact-prior upgrades, crash windows, and final API/integration certification remain `0.6.9`–`0.7.0`; process-wide logging remains `0.8.7`.

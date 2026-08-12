# ADR 0066: Scoped compliance risk register

Date: 2026-08-12

Status: Accepted for `0.7.4`

## Context

Risk work needs consistent reporting and accountable treatment without becoming a client-wide data oracle. Free-form severity is not comparable, mutable rows erase decisions, and treatment text alone cannot establish who accepted residual risk.

## Decision

- Each risk has a stable Entity identity owned by one explicit MSP or organization Workspace. It may relate to one exact-scope control assignment and one currently authorized TekDocs user owner.
- Likelihood and impact are each 1–5. TekDocs derives the 1–25 score and low, moderate, high, or critical reporting band; exact-Workspace summaries report status, band, and overdue counts.
- Treatment is mitigate, avoid, transfer, or accept. Accept requires accepted status and records the authenticated actor and time. Leaving accepted state clears only the current projection; prior acceptance remains in history.
- Every create or review appends a retained full-state decision and pins the related control revision when present. Central policy, non-disclosing lookups, PostgreSQL relationship/acceptance/retention guards, and forced RLS protect scope and history.

## Consequences

Risk reporting is consistent and acceptance is attributable without claiming remediation or certification. This slice does not add financial risk models, workflow automation, cross-client reporting, signed evidence bundles, or certification.

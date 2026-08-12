# ADR 0070: Registered-domain inventory

Date: 2026-08-12

Status: Accepted for `0.7.8`

A registered domain is a stable Entity owned by one explicit MSP or organization Workspace. Canonical identity is lowercase IDNA ASCII; the entered registrar, dates, renewal mode, owner, status, and Markdown notes are operational claims rather than observations. Registrars are same-tenant vendor/partner organizations and owners are currently authorized users, but neither edge grants access. Automated RDAP/DNS evidence remains separate so discovered data cannot silently overwrite entered records.

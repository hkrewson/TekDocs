# ADR 0106: Portable workspace manifest contract

Status: Accepted

Date: 2026-10-03

## Context

Each managed workspace repository needs enough identity metadata to be
understandable outside a running TekDocs installation. That metadata must remain
portable and forward-compatible without turning Git into the authority for
authorization, workflow or operational records.

## Decision

TekDocs writes deterministic UTF-8 YAML beneath `.tekdocs/` at the accepted
repository head:

- `repository.yml`, schema `tekdocs.repository/v1`, contains the stable
  repository UUID and its workspace UUID.
- `workspace.yml`, schema `tekdocs.workspace/v1`, contains the stable workspace
  UUID, workspace kind and display name. Organization workspaces additionally
  contain their organization UUID and sorted classifications.
- `organizations.yml`, schema `tekdocs.organization-directory/v1`, exists only
  in the MSP repository. It contains one organization entry sorted by stable
  UUID, with the organization, workspace and repository UUIDs, display name and
  sorted classifications.

PostgreSQL remains authoritative for every generated field. Regeneration
replaces those fields while retaining safe unknown fields at their existing
mapping location. Unknown organization entries are not retained because the
database-owned directory membership is authoritative. A schema identifier not
supported by the running version fails closed rather than being rewritten.

Accepted input is bounded to one MiB, eight collection levels and 50,000 YAML
nodes. Aliases, merge keys, duplicate keys, custom object tags, non-string or
secret-shaped field names, non-finite numbers, oversized strings and control
characters are rejected. Serialization sorts keys and emits stable bytes, so an
unchanged projection produces no Git commit.

The manifests never contain assets, serial numbers, users, contracts,
permissions, audit data, tokens, integration configuration or credentials.
Organization repositories never receive the MSP organization directory.

## Consequences

- Repositories can be identified and related to their TekDocs workspace without
  a database export, and organization renames do not change stable UUIDs.
- The MSP repository can enumerate organization repository identities without
  aggregating organization-authored or operational data.
- Forward-compatible metadata can survive regeneration only when it obeys the
  portable and least-data field contract.
- These manifests describe ownership identity; they do not grant access, prove
  approval, replace audit evidence or constitute a complete backup.

ADR 0105 remains the authority for the broader Markdown content graph and local
Git architecture.

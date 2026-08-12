# Migration testing

PostgreSQL migrations are the sole schema source of truth. A milestone cannot close on a fresh-install result alone: supported upgrades must preserve identifiers, ownership, archived state, authorization edges, audit evidence, and database isolation.

## Blocking migration cycle

`backend/apps/core/tests/test_migration_stabilization.py` creates representative data for the current foundation, including an organization and classification, person, site and nested location, versioned custom-field definition, typed relationship, non-owner custom role and assignment, archived record, and audit events. It reverses and reapplies the latest authorization-control-plane guard migration as well as the active RLS migration, verifying that both trigger inventories and representative identifiers survive.

The test then:

1. reverses core migration `0019_activate_runtime_rls` to `0018`;
2. verifies the RLS activation was actually removed;
3. reapplies `0019`;
4. verifies stable Entity and domain identifiers, row counts, archival state, role permissions and assignments, complete forced-RLS inventory, and database-enforced audit immutability; and
5. runs in the same `make test-stabilization` invocation as the raw non-owner runtime-role matrix and the full current permission/IDOR suite.

This is intentionally a cycle of the latest reversible isolation migration, not permission to reverse arbitrary production migrations. Before adding a non-reversible migration, its ADR and release notes must define an equivalent forward-only preservation rehearsal and rollback procedure.

## Required commands

For a focused local cycle:

```sh
docker compose run --rm migrate pytest apps/core/tests/test_migration_stabilization.py -q
```

For cross-cutting stabilization:

```sh
make test-stabilization
make test-certification
make test-documentation-certification
make test-inventory-certification
make test-network-stabilization
make test-portal-notification-certification
```

For release evidence, also run:

```sh
make clean-install-rehearsal
make upgrade-rehearsal
make documentation-upgrade-rehearsal
make documentation-backup-rehearsal
make network-upgrade-rehearsal
make network-backup-rehearsal
make portal-notification-upgrade-rehearsal
make portal-notification-backup-rehearsal
```

The general upgrade rehearsal begins from the maintained `0.1.3` schema fixture, applies current migrations through the one-shot migration owner, verifies preserved sentinel data, and starts the application under the separate runtime role. The documentation rehearsal separately begins at `0.2.8` with immutable revision history, a managed attachment, a signed STATIC publication, and retained PDF bytes. The network rehearsal begins at `0.4.7`, retains representative network records and NetBox identity, applies the current production images, then verifies exact Workspace ownership plus search/export. The controlled-client-access rehearsal begins at exact `0.5.9` and preserves client membership, publication/control identity, signed PDF evidence, outbox receipt, inbox state, SMTP queue identity, and digest/quiet-time preferences through the current release. Independent backup rehearsals capture PostgreSQL and media, restore both into clean volumes, and verify the same data. Docker-backed evidence is mandatory; a SQLite or host-only pass cannot certify migrations or RLS.

## Failure handling

- Stop the release when reversal/reapplication changes identifiers, counts, ownership, archive timestamps, role edges, RLS policy inventory, or audit immutability.
- Do not repair a failing upgrade by deleting volumes or recreating customer data.
- Add a data migration and preservation assertion for every schema change that transforms stored values.
- Never grant schema-owner or `BYPASSRLS` rights to the application role to make a migration pass.
- Record the exact source version, target version, commands, and result in the release evidence.

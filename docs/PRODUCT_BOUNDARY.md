# Product capability contract

This is the maintained capability inventory for TekDocs. `supported` means the visible product may expose the capability and the release gates cover it. `experimental` means useful implementation exists but it is not part of the 1.0 compatibility promise until the linked issue closes. `excluded` means TekDocs may integrate with an authoritative external system but must not present itself as that system.

The current column describes `0.8.46`. The 1.0 column is the release contract, not a claim about unfinished work.

| Capability | Current | Intended 1.0 | Authority and boundary | Required issue |
| --- | --- | --- | --- | --- |
| Workspaces, organizations, people, sites, files, access control, audit, recovery | supported | supported | TekDocs | — |
| Markdown documentation, reusable blocks, revision history, STATIC publication, client portal | supported | supported | TekDocs | — |
| Structured topic types and guided authoring | excluded | supported | TekDocs | [#30](https://github.com/hkrewson/TekDocs/issues/30) |
| Documentation maps, baselines, and client handoff packages | supported | supported | TekDocs | — |
| Publication preflight and documentation lint | experimental | supported | TekDocs | [#31](https://github.com/hkrewson/TekDocs/issues/31) |
| Controlled taxonomies and tag governance | supported | supported | TekDocs | — |
| Inventory, licensing, commercial records, networks, domains, certificates, reminders, compliance | supported | supported | TekDocs records documented state; external systems may supply observations | — |
| Entity-linked and authored diagrams | experimental | supported | TekDocs for authored diagrams and retained exports | [#41](https://github.com/hkrewson/TekDocs/issues/41), [#44](https://github.com/hkrewson/TekDocs/issues/44) |
| Unified workspace search | experimental | supported | TekDocs | [#27](https://github.com/hkrewson/TekDocs/issues/27) |
| Bulk import and dry-run reconciliation | experimental | supported | TekDocs | [#28](https://github.com/hkrewson/TekDocs/issues/28) |
| Provider-neutral integration framework | experimental | supported | External system remains authoritative unless a connector contract says otherwise | [#34](https://github.com/hkrewson/TekDocs/issues/34) |
| Microsoft 365/Entra/Intune, HaloPSA, and NinjaOne projections | excluded | supported | Named external systems | [#35](https://github.com/hkrewson/TekDocs/issues/35), [#36](https://github.com/hkrewson/TekDocs/issues/36), [#37](https://github.com/hkrewson/TekDocs/issues/37) |
| Invoice drafting, issuance, delivery, retained PDF/CSV | experimental | supported | TekDocs issues invoices; accounting systems own the ledger and settlement | [#33](https://github.com/hkrewson/TekDocs/issues/33) |
| Native ticketing/PSA workflow | excluded | excluded | External PSA or help desk | [#58](https://github.com/hkrewson/TekDocs/issues/58), [#36](https://github.com/hkrewson/TekDocs/issues/36) |
| General ledger, expenses, purchasing, payroll, tax filing | excluded | excluded | External accounting/payroll system | [#48](https://github.com/hkrewson/TekDocs/issues/48) |
| Payment processing | excluded | excluded | External payment processor | [#49](https://github.com/hkrewson/TekDocs/issues/49) |
| CRM, lead management, and sales pipeline | excluded | excluded | External CRM/PSA | [#46](https://github.com/hkrewson/TekDocs/issues/46) |
| RMM, MDM, endpoint security, backup control, cloud control planes, DNS/network controllers | excluded | excluded | External systems; TekDocs may project documented observations | [#47](https://github.com/hkrewson/TekDocs/issues/47), [#51](https://github.com/hkrewson/TekDocs/issues/51), [#52](https://github.com/hkrewson/TekDocs/issues/52), [#53](https://github.com/hkrewson/TekDocs/issues/53), [#54](https://github.com/hkrewson/TekDocs/issues/54), [#55](https://github.com/hkrewson/TekDocs/issues/55), [#56](https://github.com/hkrewson/TekDocs/issues/56) |
| Credential-value custody | excluded | excluded | Password manager; TekDocs stores references only | [#50](https://github.com/hkrewson/TekDocs/issues/50) |
| Hosted multi-MSP control plane | excluded | excluded | Separate future product decision | [#21](https://github.com/hkrewson/TekDocs/issues/21) |

## Deterministic product decisions

- The visible product says **Invoices**, uses `/invoices`, and retains `/accounting` only as a compatibility redirect.
- Tickets are not a TekDocs capability or route. Ticket state may appear only as a permission-filtered projection from an external system.
- Navigation, routes, contextual help, backend workspace payloads, and tests use the maintained capability registries and must remain in parity.
- Unsupported deep links return a neutral unavailable result. They do not advertise roadmap work.

## Integration principle

TekDocs is the system of record for structured documentation and the relationships it authors. A system of action remains authoritative for its own workflow. Integrations use explicit external identifiers, minimum necessary projections, read/reconcile behavior by default, and separately approved write scopes.

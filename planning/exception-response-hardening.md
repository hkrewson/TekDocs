# Exception response hardening

Status: implementation complete; exact-source hosted CodeQL remains the final
alert authority. Owner: maintainer / pre-1.0 security closeout.

This bounded slice addresses the exception families most likely to turn an
implementation diagnostic into a public API response. It does not dismiss or
hide the remaining `py/stack-trace-exposure` queue, change response status codes,
or redefine intentional domain conflict messages.

## Acceptance criteria

- Generic exception translators never derive public response text from
  `str(exception)`, exception arguments, or framework message collections.
  An intentional domain message must use a dedicated public-detail contract.
- The selected inventory, invoicing, stock, content-index, data-flow, network,
  and repository-publication handlers return fixed, operation-specific text.
- Existing HTTP 400 and 409 behavior, response shapes, delivery-failure audit
  recording, and database-conflict messages remain intact.
- Regression tests inject private diagnostic strings and prove they do not reach
  API details.
- The exception-boundary guard is part of the backend image security gates.
- Exact-source CodeQL determines which alerts close and provides the inventory
  for the next bounded remediation slice.

## Disposition

The November 8, 2026 shipped-code inventory contained 127 open
`py/stack-trace-exposure` alerts. Review separated 19 ambiguous sites from 108
sites whose current messages appear to be bounded domain or conflict text. The
19 sites share eleven response families: six generic translators plus content
indexing, asset network records, invoice/service-rate operations, stock
operations, and repository publication evidence.

Those families now choose fixed text at the view boundary. Data-flow and network
domain refusals retain their useful bounded reason through an explicit
`public_detail` contract; model-validation diagnostics use fixed text. The
data-flow exception string itself is generic. Exception chaining is retained for
server-side causality, while generic caught exception objects no longer supply
public message content. Integrity-conflict text remains fixed and useful.
The repository-publication path retains HTTP 409; validation paths retain HTTP
400; invoice delivery still records an unconfirmed attempt before returning its
bounded retry-safe message.

No migration, OpenAPI shape, persistence contract, authorization decision, or
production configuration changes in this slice. The remaining 108 alerts are
not accepted as safe by implication: each still requires an exact handler review
and either evidence-backed dismissal or a later fixed-message change before 1.0.

## Validation

The red regression first failed all eleven affected response families because
their public text was derived from caught exceptions. After the implementation,
the focused boundary suite passes 29 cases, including injected private database
and model-validation diagnostics plus explicit bounded domain details. Data-flow,
network, inventory, stock, invoice, and content-composition suites pass against
the retained `tekdocs` development services. Ruff, targeted mypy, Django system
checks, and migration drift checks also pass. Hosted Build and CodeQL remain
required on the pushed commit.

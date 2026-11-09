# Exception response hardening

Status: the first two bounded slices are confirmed by exact-source Build and
CodeQL; the document-operation and publication slice is locally complete and
awaits exact-source hosted validation. Owner: maintainer / pre-1.0 security
closeout.

This bounded slice addresses the exception families most likely to turn an
implementation diagnostic into a public API response. It does not dismiss or
hide the remaining `py/stack-trace-exposure` queue, change response status codes,
or redefine intentional domain conflict messages.

## Acceptance criteria

- Generic exception translators never derive public response text from
  `str(exception)`, exception arguments, or framework message collections.
  An intentional domain message must use a dedicated public-detail contract.
- The selected inventory, invoicing, stock, content-index, data-flow, network,
  repository-publication, document-operation, export, composition and static
  publication handlers use explicit public response contracts.
- Existing HTTP 400 and 409 behavior, response shapes, delivery-failure audit
  recording, and database-conflict messages remain intact.
- Regression tests inject private diagnostic strings and prove they do not reach
  API details.
- The exception-boundary guard is part of the backend image security gates.
- Exact-source CodeQL determines which alerts close and provides the inventory
  for the next bounded remediation slice.

## Disposition

The November 8, 2026 repository-wide alert view contained 127 open
`py/stack-trace-exposure` alerts, but that view combines stale Build analyses and
non-default branch instances. The exact standalone Python analysis at `4dbe9b80`
contained 131 shipped-source results. The first slice selected 19 ambiguous
results across eleven response families: six generic translators plus content
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

Exact-source CodeQL run 42551427527 reduced those stack-trace results from 131 to
112, closing exactly the selected 19. The repository-wide alert count remains
inflated by the older `.github/workflows/build.yml:analyze` configuration and
branch instances; no alerts were dismissed to obtain this result.

The second bounded slice covers all fourteen remaining invoice-view results and
the directly connected stock-view result. `InvoiceError` and `StockError` now
carry explicit public details. Framework validation is translated to fixed
invoice or stock text before those exceptions are created, while established
business refusals such as insufficient on-hand quantity remain useful. This
follow-up reduced the exact queue from 112 to 97 in CodeQL run 42552963371,
closing exactly those fifteen selected paths without dismissals.

The third bounded slice selects the largest remaining single handler family:
all twelve results in `document_views.py`. Document operations, composition,
exports and static publication conflicts now separate their internal exception
string from an explicit `public_detail`. Taxonomy, content-key and isolated
diagram-renderer refusals propagate only their reviewed domain detail through
nested exceptions. Both publication implementations catch the renderer's
specific safe error type; an unexpected `ValueError` is no longer translated
into a public 409 response. Established conflict text, response shapes and
status codes remain unchanged.

No migration, OpenAPI shape, persistence contract, authorization decision, or
production configuration changes in either slice. The remaining exact results
are not accepted as safe by implication: each still requires a handler review
and either evidence-backed dismissal or a later fixed-message change before 1.0.

## Validation

The first red regression failed all eleven affected response families because
their public text was derived from caught exceptions. After the implementation,
the focused boundary suite passes 29 cases, including injected private database
and model-validation diagnostics plus explicit bounded domain details. Data-flow,
network, inventory, stock, invoice, and content-composition suites pass against
the retained `tekdocs` development services. Ruff, targeted mypy, Django system
checks, and migration drift checks also pass. Build 42544014776 and CodeQL
42551427527 confirm the first slice on exact source.

For the invoice/stock follow-up, injected Django validation and stock-allocation
diagnostics first demonstrated the unsafe translation paths. The first broad
test exposed an over-broad replacement that removed the established on-hand
quantity response; the final public-detail boundary preserves that response.
The boundary suite and the complete targeted invoice-draft, issue, delivery,
stock-inventory, and recurring-invoice files pass against retained PostgreSQL.
Ruff, targeted mypy, Bandit, Django checks, and migration-drift checks pass.
Exact-source CodeQL 42552963371 confirms the expected fifteen-result reduction.
Build 42552901893 failed only the existing business-error compatibility assertion
because the first implementation also replaced `StockError`'s internal string.
The reproduced correction retains the bounded internal field-validation message
while keeping `public_detail` fixed. The exact failed test, boundary suite, and
stock/invoice suites passed locally. Corrected-source Build 42559060835 passed
the final validation job, and exact-source CodeQL 42559099854 passed both
languages and retained the expected 97-result queue.

For the document/publication slice, the exact CodeQL results reproduced all
twelve direct caught-exception reads before the change. The boundary suite and
the complete focused document, key-resolution, diagram-publication,
Git-publication and migration-inventory suites pass against the retained
development PostgreSQL service. Ruff, full backend mypy, Bandit, Django system
checks and migration-drift checks pass. The self-review covered every direct
constructor and dynamic nested-exception wrapper for the affected domain types.
Exact-source Build and CodeQL remain required after push; no alert is dismissed
or counted closed before that evidence exists.

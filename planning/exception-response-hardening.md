# Exception response hardening

Status: the first four bounded slices are confirmed by exact-source Build and
CodeQL. Exact-source CodeQL confirms the catalog-handler slice; its Build rerun
was inconclusive after an unrelated template-migration shard reached its runner
time limit. The software-inventory handler slice is locally complete and awaits
exact-source hosted validation. Owner: maintainer / pre-1.0 security closeout.

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
status codes remain unchanged. Exact-source CodeQL run 42565622117 reduced the
queue from 97 to 85, closing exactly those twelve selected paths; Build
42565561039 passed its final validation job.

The fourth bounded slice selects all nine results in `inventory_views.py`.
Inventory, asset-CSV and software-inventory exceptions now separate internal
diagnostics from an explicit public detail. Django model-validation text maps to
fixed hardware or software inventory explanations, and CSV row wrappers carry
only the nested public detail across the import boundary. Existing controlled
inventory business refusals remain the default public detail. Retained
publication downloads reuse the previously reviewed publication conflict
contract.

Exact-source CodeQL run 42628004806 reduced the queue from 85 to 76, closing
exactly the nine selected inventory paths; Build 42627936205 passed its final
validation job. GitHub's repository-wide open-alert view reports 464 alerts,
but 127 belong to the retired `.github/workflows/build.yml:analyze`
configuration at `ef6c57c`. The current standalone configuration contributes
337 alerts across all rules, led by 161 cyclic-import and 72 unused-import
results. This work queue intentionally tracks the 76 current
`py/stack-trace-exposure` SARIF results rather than conflating those categories.

The fifth bounded slice selects all eight results in `catalog_views.py`.
`CatalogError` now separates its internal diagnostic from an explicit public
detail. The fixed stale-revision response exposes the same bounded message and
current-revision payload as before, and the catalog-document association reuses
the previously reviewed inventory error contract. Existing schema-validation
feedback remains an intentional catalog-domain message; database conflicts keep
their fixed response.

Exact-source CodeQL run 42671675386 passed on attempt 2 and reduced the queue
from 76 to 68, closing exactly the eight catalog paths. Build run 42671601875
executed the source, security, browser and database work on attempt 2, but the
unrelated `template-migration-a` shard reached its 30-minute runner limit and
the final gate failed closed. That run is retained as incomplete Build evidence,
not catalog acceptance.

The sixth bounded slice selects all seven results in
`software_inventory_views.py`: the workspace ownership denial and six software
installation/license mutation handlers. Both established domain exception types
already separate internal diagnostics from `public_detail`; the view now uses
that contract consistently. Existing controlled messages such as exhausted-seat
and inactive-license refusals remain public, with their established 400/403
statuses and error envelope unchanged.

No migration, OpenAPI shape, persistence contract, authorization decision, or
production configuration changes in these slices. The remaining exact results
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
Build 42565561039 passed the final validation job. CodeQL 42565622117 passed both
languages and evidence delivery and confirmed the expected twelve-result
reduction to 85.

For the inventory-handler slice, the exact SARIF reproduced all nine direct
caught-exception reads before the change. Tests inject private hardware and
software model diagnostics, verify the internal string remains available to the
server, and prove only fixed public details cross the response contract. A CSV
row-wrapper regression proves nested internal text does not become its public
detail. The boundary/business-error suites and the complete inventory suite pass
against the retained development PostgreSQL service. Build 42627936205 passed
its final validation job. CodeQL 42628004806 passed both languages and evidence
delivery and confirmed the expected nine-result reduction to 76.

For the catalog-handler slice, the exact SARIF reproduced all eight direct
caught-exception reads before the change. The endpoint regression injects a
private catalog diagnostic and proves only the explicit domain detail reaches
the 400 response. The stale-revision test preserves its 409 status, fixed detail
and current-revision payload. The boundary, complete catalog and complete
inventory suites pass against retained PostgreSQL. Exact-source CodeQL
42671675386 confirms the expected eight-result reduction to 68. Build
42671601875 attempt 2 remains incomplete because the unrelated
template-migration shard was cancelled at its runner time limit; it is not
represented as passing acceptance.

For the software-inventory handler slice, the exact analysis reproduced all
seven direct caught-exception reads before the change. The static boundary guard
first failed on the module, then passed after every handler used
`public_detail`. Direct DRF response tests inject distinct private software and
workspace diagnostics and prove neither reaches the public error envelope. A
control retains the existing exhausted-seat domain message. The complete
exception-response boundary suite passes locally. Exact-source Build and CodeQL
remain required after push; the expected CodeQL queue is 61 and no alert is
dismissed in advance.

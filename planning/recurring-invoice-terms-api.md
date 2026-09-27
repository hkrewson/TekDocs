# Recurring terms amendment API — 0.8.46 checkpoint

Issue #76 pre-1.0 implementation checkpoint. Version remains `0.8.46`. This
slice exposes the retained effective-terms foundation through a reviewed,
short-lived operator API. It does not yet add the amendment form to the
Recurring invoices screen.

## Workflow

1. The operator reads the schedule detail and current source review. The source
   response supplies the current digest and installation business date.
2. `POST .../recurring-invoices/{schedule}/terms/preview` receives the expected
   current terms id, current source digest, future effective period, and proposed
   sell terms.
3. Preview rechecks invoice edit/view and cost-view permission, MFA, exact client
   scope, source availability, schedule state, expected latest terms, current
   source digest, claimed periods, full-period alignment, currency, money, and
   tax validity under the established lock order.
4. The response compares current and proposed description, quantity, price,
   currency, due days, tax version, and exact net/tax/total. It reports whether
   the newly reviewed source differs from the source retained on the current
   terms. The response contains a signed, actor/tenant/client/schedule-bound token
   that expires after 15 minutes.
5. `POST .../terms/apply` accepts only that token. Apply rechecks current
   permissions and all mutable conditions, then appends the next immutable terms
   version and its value-minimized audit event in one transaction.

The server supplies the business date. Clients cannot backdate a preview by
posting their own clock value. Unknown financial fields are rejected by the
strict request serializer.

## Retry and conflict behavior

Apply is safe to retry while the signed review remains valid. If the exact next
version was already committed by the same actor from the same source digest,
effective date, and proposed values, the endpoint returns that retained row and
does not create another version or audit event.

Any different newer terms, source drift, newly claimed boundary, stopped
schedule, expired or altered token, other actor, tenant/client mismatch, or
permission change returns a conflict or denial. Values are never inferred from
the current request during apply; the signed preview is the sole mutation input.
Database uniqueness and insertion guards remain the final concurrent-write
boundary.

## Compatibility and contracts

The two routes are additive. Existing enrollment, due discovery, draft
preview/apply, stop, and schedule-detail contracts remain unchanged. Both routes
are registered in the central permission inventory as organization-scoped
`invoices.edit` mutations; the views additionally require invoice and cost
visibility. OpenAPI and generated browser types include the amendment request,
comparison, and response shapes.

No migration is added by this slice. The migration and recovery classification
remain documented in
[recurring-invoice-terms-versions.md](recurring-invoice-terms-versions.md).

## Verification evidence

- Exact preview totals and successful apply of version two.
- Idempotent retry returns the first retained version and leaves one audit event.
- A refreshed source can be explicitly approved; later source drift invalidates
  the signed review.
- Claimed boundaries, stopped schedules, altered/expired tokens, and actor
  mismatches fail without appending terms.
- Cross-client paths, missing MFA, and unreviewed request fields fail closed.
- The complete focused recurring-invoice suite, central route-inventory check,
  OpenAPI generation/check, lint, and migration/model drift checks cover the
  checkpoint.

## Next slice

Add the operator workflow to the Recurring invoices surface. It must show the
current and proposed values side by side, source-change status, exact totals,
effective period, retained history, preview expiry, uncertain-apply retry, and
dirty-form navigation protection. Stopped schedules remain history-only.

Deployment, external push, Wiki publication, and a version change remain outside
this checkpoint.

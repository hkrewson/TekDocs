# Account, staff and access administration checkpoint

Status: implemented at 0.8.46; broad release acceptance remains open.

## Result

`/settings`, `/staff` and `/access-control` now expose one focused management area at a time. Every area has a direct URL and uses the shared desktop section navigation or the labeled mobile Sections menu. Refresh and browser history preserve the selected area, while direct route visits fall back to the safest first section.

Settings separates Profile, Two-factor authentication, Active sessions and API tokens. This keeps passwords, recovery codes and one-time token values inside their existing confirmation and disclosure boundaries. Profile changes participate in the shared dirty-form guard. API-token creation opens only on request in a background-locking editor, retains a failed draft, and requires explicit discard before closing a changed form.

Staff separates invitation history from joined MSP members. Invitation search, status, page and 25/50/100 page size are URL-addressed. The former wide history table is a compact list that keeps email identity and state visible while labeling sent, expiry and attempt facts. Invitation creation opens in a focused editor and protects a typed address. Resend and revoke retain their consequence-first confirmation.

Access Control separates MSP members, client access modes, staff assignments, custom roles and built-in role reference. Only the selected area renders; custom-role APIs are not requested until that area opens. Existing role, access-mode, staff-assignment, custom-role and collection authorization remains server-owned, and consequential changes still require review and confirmation.

## Compatibility and limits

No API, schema, permission or domain-data change is included. Existing `/settings`, `/staff` and `/access-control` links remain valid and choose curated defaults. New `section`, invitation search/filter/page and page-size query parameters are additive. This checkpoint does not change account activation or sign-in screens, and it does not claim final technician, screen-reader, native zoom, production-image or release acceptance.

## Verification

Focused component tests cover all three routes, direct section URLs, existing denial and failed-mutation retention, invitation pagination/filtering, sensitive confirmations and token disclosure. `frontend/e2e/account-access-layout.spec.ts` passes 18 cases across Chromium, Firefox and WebKit at 320, 390, 768, 1024, 1280 and 1440 CSS-pixel widths, including short viewports, URL state, long values, overlay background locking, accessibility and page-overflow assertions.

The isolated real browser-to-Django-to-PostgreSQL journey passes in 3.6 minutes. Its first run exposed a successful invitation save that closed the editor before retiring its dirty-form registration; the fixed transition and component regression test now permit immediate navigation without a false discard prompt. The repository gate passes all 656 frontend tests in 119 files, backend static and migration checks, schema/generated contract drift, documentation policy, the production build and compressed bundle budgets (shell 130402 <= 131072; shell style 24400 <= 24576).

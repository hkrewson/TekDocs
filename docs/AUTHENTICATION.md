# Browser authentication contract

TekDocs uses `django-allauth` headless browser APIs with Django’s server-side session and CSRF middleware. The React application does not mint tokens, store passwords, or treat hidden UI as authorization.

## Initial state

The browser requests both:

- `GET /api/v1/bootstrap/status`, which returns only `bootstrap_required`;
- `GET /_allauth/browser/v1/auth/session`, which establishes the readable CSRF cookie and returns authenticated or anonymous session state.

When bootstrap is required, the shell is not rendered. The setup form submits the deployment token only in `X-TekDocs-Bootstrap-Token`; it is never placed in a URL, JSON body, local storage, session storage, cookie, log, or rendered error. Password fields are cleared when submission starts.

A successful bootstrap creates the tenant, first owner, and owner membership; records the owner’s deployment-asserted email as the verified primary allauth address; and immediately performs a normal allauth password login.

## Session lifecycle

- Login: `POST /_allauth/browser/v1/auth/login` with same-origin credentials and `X-CSRFToken`.
- Logout: `DELETE /_allauth/browser/v1/auth/session` with same-origin credentials and `X-CSRFToken`.
- Shell context: `GET /api/v1/auth/context`; it requires an authenticated session and an explicit membership in the installation tenant.

The shell renders only after the allauth session and TekDocs context both succeed. The owner and accounts created from accepted invitations receive tenant membership; unrelated identities remain denied. Invitation administration continues to require installation ownership until scoped roles are implemented.

`0.0.8` enables allauth’s maintained user-session inventory with activity tracking. `GET /_allauth/browser/v1/auth/sessions` returns only the authenticated user’s browsers. The Settings page identifies the current browser and exposes CSRF-protected revocation of another session through `DELETE` on the same endpoint. The server scopes submitted IDs to the requesting user before ending the underlying Django session. A password change continues to invalidate every password-bound session regardless of whether an inventory row exists.

`0.0.6` adds controlled invitation acceptance. The browser reads the token from the URL fragment, removes the fragment immediately, and submits the token with account details only in a CSRF-protected request body. Successful acceptance creates one active user, verified primary allauth email, and tenant membership before consuming the invitation and establishing a normal Django session. See `docs/INVITATIONS.md` for the lifecycle and deployment contract.

Login errors shown by TekDocs do not distinguish an unknown address from a wrong password.

## Password recovery

`0.0.7` uses allauth’s headless password-reset request and completion endpoints with Django’s maintained password-reset token generator. Request responses and browser confirmation copy do not reveal whether an address belongs to an active account. The default expiry is one hour and can be reduced or increased from five minutes to 24 hours with `PASSWORD_RESET_TIMEOUT_SECONDS`.

The reset email points to `TEKDOCS_PUBLIC_URL` with the opaque key in the URL fragment. The browser removes that fragment immediately, validates the key through the allauth header contract, and submits it only in a CSRF-protected request body. The key is not stored in local storage, session storage, cookies, application logs, or API URLs.

A completed reset does not sign the user in. Changing the password invalidates the key and Django’s password-derived session authentication hash, so every existing session is rejected on its next request. The user returns to sign-in with the new password.

## Abuse limits and authentication audit

Rate-limit counters use the shared `DJANGO_CACHE_URL` Valkey database rather than worker-local memory. Current policy permits 20 login requests per minute per IP; failed logins are limited to 10 per minute per IP and five per ten minutes per account key. Password-reset requests are limited to 10 per hour per IP and three per hour per account key; reset-key completion is limited to 10 per hour per IP. Rate-limit responses never include account existence details.

Append-only audit actions cover successful and failed login, logout, completed password reset, session client changes, and explicit session revocation. Events associate the installation tenant and an authorized actor when known, plus the request correlation ID. Audit metadata is empty: email addresses, submitted credentials, IP addresses, user agents, session keys, and inventory IDs are deliberately excluded.

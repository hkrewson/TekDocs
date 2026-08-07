# Browser authentication contract

TekDocs uses `django-allauth` headless browser APIs with Django’s server-side session and CSRF middleware. The React application does not mint tokens, store passwords, or treat hidden UI as authorization.

## Initial state

The browser requests both:

- `GET /api/v1/bootstrap/status`, which returns only `bootstrap_required`;
- `GET /_allauth/browser/v1/auth/session`, which establishes the readable CSRF cookie and returns authenticated or anonymous session state.

When bootstrap is required, the shell is not rendered. The setup form submits the deployment token only in `X-TekDocs-Bootstrap-Token`; it is never placed in a URL, JSON body, local storage, session storage, cookie, log, or rendered error. Password fields are cleared when submission starts.

A successful bootstrap creates the tenant and first owner, records the owner’s deployment-asserted email as the verified primary allauth address, and immediately performs a normal allauth password login. This first-owner exception is necessary before invitation issuance in `0.0.5` and verified-email activation in `0.0.6`; later users do not inherit it.

## Session lifecycle

- Login: `POST /_allauth/browser/v1/auth/login` with same-origin credentials and `X-CSRFToken`.
- Logout: `DELETE /_allauth/browser/v1/auth/session` with same-origin credentials and `X-CSRFToken`.
- Shell context: `GET /api/v1/auth/context`; it requires an authenticated session and, during the bootstrap-only release, the installation-owner identity.

The shell renders only after the allauth session and TekDocs context both succeed. A session-authenticated identity that is not the installation owner receives a denial until controlled invitations and scoped roles are implemented.

Login errors shown by TekDocs do not distinguish an unknown address from a wrong password. Authentication audit events, session inventory/revocation, and expanded throttling remain scoped to `0.0.8`; allauth’s maintained login rate-limit path remains enabled in the interim.

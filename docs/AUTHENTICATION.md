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

`0.0.6` adds controlled invitation acceptance. The browser reads the token from the URL fragment, removes the fragment immediately, and submits the token with account details only in a CSRF-protected request body. Successful acceptance creates one active user, verified primary allauth email, and tenant membership before consuming the invitation and establishing a normal Django session. See `docs/INVITATIONS.md` for the lifecycle and deployment contract.

Login errors shown by TekDocs do not distinguish an unknown address from a wrong password. Password reset remains `0.0.7`. Authentication audit expansion, session inventory/revocation, and throttling remain scoped to `0.0.8`; allauth’s maintained login rate-limit path remains enabled in the interim.

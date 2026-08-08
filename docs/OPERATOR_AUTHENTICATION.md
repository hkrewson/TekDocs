# Authentication operator runbook

This runbook covers the authentication operations available through TekDocs `0.0.11`. It does not create an emergency authentication bypass. Perform changes from an encrypted administrative workstation, keep deployment secrets outside the repository, and preserve the append-only audit trail.

## Before enabling access

1. Generate deployment values with `make bootstrap`, then move production values into the deployment secret store. Never commit `.env`.
2. Configure the final HTTPS public URL, exact allowed hosts and CSRF origin, secure cookies, HSTS, SMTP TLS, and a stable 256-bit `TEKDOCS_MASTER_KEY`.
3. Back up the PostgreSQL volume and every deployment-supplied encryption/signing key separately. A database backup without the original master key cannot decrypt enrolled MFA data.
4. Run `make test-compose` and `make test-auth-abuse`. Production configuration validation must pass before the service is exposed.

The deployment token is accepted only while the installation is unclaimed. Retrieve it from the deployment secret store, submit it through the first-owner screen, and remove routine operator access to it after bootstrap. Rotating the environment value does not replace or create the owner.

## Invitations and account lifecycle

Only the installation owner can issue, resend, or revoke invitations in the current release. Invitations are single-use, expire, and store only a token digest. Resending invalidates the former link. Check SMTP delivery before inviting users; do not copy invitation links into tickets or logs.

If delivery fails, correct SMTP configuration and resend the existing pending invitation. Revoke an invitation immediately when the recipient or address is wrong. Account disablement and scoped administrative delegation arrive in later milestones; do not treat invitation revocation as removal of an already accepted account.

## Password and session incidents

Password recovery deliberately gives the same browser response for known and unknown addresses. Confirm mail delivery from the SMTP service rather than inferring account existence from the response. Reset links expire, are single-use, and invalidate password-bound sessions after completion.

For a suspected stolen session:

1. From Settings → Security, revoke every other recorded browser session.
2. Change the account password through the recovery flow if password compromise is possible.
3. Review append-only authentication events for login, MFA, password-reset, and session-revocation actions. Events intentionally exclude email addresses, credentials, IP addresses, user agents, codes, and session identifiers.
4. Preserve application and reverse-proxy logs under the incident-retention policy. Do not increase logging to include request bodies or authentication headers.

## MFA enrollment and recovery

Owners must enroll TOTP before privileged invitation administration. Scan the locally generated QR code or enter its manual key, confirm a current code, and store the one-time recovery-code set in an approved password manager. TekDocs never emails those values and cannot show the same set again.

An owner with an unused recovery code can use it at the MFA challenge, reauthenticate with the password, and replace all recovery codes. Replacing codes invalidates the prior set. Disabling TOTP also requires recent password reauthentication and removes both the authenticator and recovery-code seed.

There is no operator bypass or administrative MFA reset in `0.0.11`. If the sole owner loses the authenticator and every recovery code, stop making account changes, preserve the database and master key, and recover a known-good backup or escalate for a reviewed recovery procedure. Direct database edits are unsupported because they bypass policy and audit guarantees.

## OIDC rollout and rollback

Configure all five OIDC values together: provider ID, display name, HTTPS discovery URL, client ID, and client secret. Register the callback shown in `docs/AUTHENTICATION.md`. Partial or malformed configuration prevents startup. Provider secrets belong in the deployment secret store.

Before announcing SSO:

1. Keep password access available for the owner.
2. Test with an existing invited account whose provider email claim is verified and exactly matches TekDocs.
3. Confirm the provider rejects an uninvited identity and that a failed/unknown provider returns safely to the sign-in surface rather than creating an account.
4. Confirm callback, issuer, audience, signature, state, and final public-origin behavior through the real reverse proxy.

To roll back, remove all five OIDC settings and recreate the application containers. Existing local accounts and password login remain authoritative. TekDocs does not store provider access or refresh tokens.

## Upgrade rehearsal

Run `make upgrade-rehearsal` before releasing or applying a new minor version. The command exports the supported `0.0.10` source into a temporary directory, starts an isolated Compose project, creates representative owner, membership, password, verified-email, encrypted-TOTP, and audit data, then starts the current source against the same PostgreSQL volume and verifies those invariants. Its project name, ports, directory, and volumes are isolated; cleanup removes only those disposable resources.

Override `TEKDOCS_UPGRADE_FROM_REF` only when deliberately rehearsing another reviewed baseline commit. A passing rehearsal supplements—never replaces—a current encrypted backup and a restore test on representative deployment data.

## Verification and escalation

- `make test-auth-abuse`: authentication enumeration, session rotation/invalidation, CSRF, closed signup, invitation boundary, and disabled-provider behavior.
- `make test-e2e-all`: critical browser and axe accessibility journeys in Chromium, Firefox, and WebKit.
- `make test-compose`: production-shaped PostgreSQL, Valkey, SMTP, migration, and application checks.
- `make release-gate`: the complete local release contract, including the upgrade rehearsal.

See `docs/AUTHENTICATION.md`, `docs/INVITATIONS.md`, `docs/EMAIL.md`, `docs/SECURITY.md`, and `docs/THREAT_MODEL.md` for the normative browser and deployment contracts.

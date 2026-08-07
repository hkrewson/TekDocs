# Email delivery

TekDocs sends its own transactional messages through Django's maintained SMTP backend and the `apps.core.email` template boundary. Text and HTML alternatives are rendered from repository templates; feature code should not build ad hoc messages or log recipients and contents.

## Local development

The default Compose stack sends SMTP to the pinned Mailpit service on the internal container network. Open <http://127.0.0.1:8025> to inspect captured messages. The UI is deliberately bound to loopback, while port 1025 is not published to the host.

The image is an immutable upstream development digest because the available stable tags carry fixed-but-unshipped High-severity dependency findings as of this release. It is development-only, passes the same blocking image scan as application containers, and should move to the next clean stable tag when upstream publishes one.

Mailpit persists up to 500 development messages in the `mailpit_data` volume. Do not use real customer addresses, personal information, secrets, or production message bodies in this inbox.

Run an explicit delivery check with:

```sh
make mail-test EMAIL_TO=you@example.com
```

The command reports only whether the backend accepted one message. It does not echo the recipient, SMTP credentials, or message body.

## Production SMTP

Set the following deployment values:

- `EMAIL_HOST` and `EMAIL_PORT`;
- `DEFAULT_FROM_EMAIL`, containing one valid sender address;
- `EMAIL_HOST_USER` and `EMAIL_HOST_PASSWORD` together when authentication is required;
- exactly one of `EMAIL_USE_TLS=true` for STARTTLS or `EMAIL_USE_SSL=true` for implicit TLS;
- `EMAIL_TIMEOUT`, in seconds.

`TEKDOCS_ALLOW_INSECURE_SMTP=true` is an explicit exception for a trusted private SMTP hop such as the local Mailpit container. It must not be used to send mail across an untrusted network. Production startup fails when SMTP configuration is incomplete, contradictory, or unexpectedly plaintext.

Mail delivery remains synchronous. `0.0.5` adds invitation templates and explicit owner-triggered resend; automatic queues, retry policy, recovery flows, notifications, and bounce handling remain separate roadmap work. Invitation SMTP failures retain a pending record without returning the address, token, or backend exception.

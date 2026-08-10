# Credential references

TekDocs records where an authorized technician can find a credential; it does not hold the credential. A reference has a title, provider, MSP-or-client workspace scope, and provider-owned pointer. There are no password, username, token, recovery-code, secure-note, or revealed-value fields.

## 1Password Private Links

Open the item in 1Password, choose **Share**, then **Copy Private Link**. This is not the public **Share** link that creates a separately accessible shared copy. The recipient must already have access to the original vault and must unlock or sign in to 1Password.

TekDocs currently accepts the unmodified canonical link with:

- HTTPS scheme;
- exact `start.1password.com` host and `/open/i` path;
- exactly one 26-character lowercase account, vault, and item identifier;
- a 1Password-owned account host ending in `.1password.com`, `.1password.ca`, or `.1password.eu`;
- no credentials, custom port, fragment, duplicate parameter, extra parameter, or alternative serialization.

Public `share.1password.*` links, arbitrary web URLs, app deep links, and malformed/modified Private Links fail closed. This strict grammar is based on current Copy Private Link output; if 1Password changes it, TekDocs will reject the new form until the adapter and fixed corpus are reviewed.

## Authorization and custody

`credential_references.view`, `credential_references.manage`, and `credential_references.open` are independent, scope-aware permissions. Read-only and documentation permissions do not imply access. Lists expose the title and provider but omit the Private Link. Search covers titles only.

**Open in 1Password** follows an authenticated TekDocs route. The server rechecks workspace reachability plus view/open permissions, revalidates the stored link, records an append-only event with empty metadata, and redirects the new browser tab to 1Password. TekDocs does not call a 1Password retrieval API or see what happens after that handoff.

Archiving removes only the TekDocs pointer. It does not delete, move, share, revoke, or otherwise change the 1Password item.

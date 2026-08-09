import unifiNetworkSetupGuide from './examples/unifi-network-setup-guide.md?raw'

export const markdownFixture = unifiNetworkSetupGuide

export const markdownDialectFixture = `## TekDocs formatting fixture

Use ==semantic highlight== for information that needs attention without implying danger.

~~Retired guidance~~ remains visible when its history matters.

- [x] Export the current configuration
- [ ] Confirm the rollback owner

> [!WARNING]
> Rebooting this switch will disconnect the site.

| Port | Purpose |
| :--- | ---: |
| 1 | WAN |

Documented exception.[^exception]

[^exception]: Approved by the change owner.
`

export const markdownRoundTripFixture = `${markdownFixture.trim()}\n\n---\n\n${markdownDialectFixture}`

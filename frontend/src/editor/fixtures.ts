export const markdownFixture = `# Firewall replacement

This procedure covers **planned replacement** of the edge firewall for [Example Client](tekdocs://entity/00000000-0000-4000-8000-000000000001).

## Preparation

- [ ] Export the current configuration
- [ ] Confirm the maintenance window
- [ ] Record the rollback owner

> Never copy managed credentials into a document.

| Check | Owner |
| --- | --- |
| ISP handoff | Network team |
| Configuration | Assigned technician |

1. Verify the serial number.
2. Apply the approved configuration.
3. Run the validation command:

\`\`\`shell
ping -c 4 192.0.2.1
\`\`\`

---

Use \`tekdocs://entity/{uuid}\` links for stable object references.
`

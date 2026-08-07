# Frontend Invariants

- Markdown is canonical. Editor HTML or JSON is never authoritative storage.
- Never render unsanitized HTML or introduce unsafe DOM sinks.
- Hidden or disabled controls are not authorization. Every privileged operation must handle a server denial safely.
- Shared-block editing must disclose reuse impact and offer detach behavior when canonical editing is unavailable.
- MSP-private and client-visible content must be visually unambiguous.
- New workflows include keyboard, responsive, loading, empty, error, and accessibility states.
- Follow the TekDocs design tokens and restrained application-shell patterns. Do not copy CollectZ source or assets and do not introduce decorative dashboard filler.

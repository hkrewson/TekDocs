# Frontend Invariants

- Markdown is canonical. Editor HTML or JSON is never authoritative storage.
- Never render unsanitized HTML or introduce unsafe DOM sinks.
- Hidden or disabled controls are not authorization. Every privileged operation must handle a server denial safely.
- Shared-block editing must disclose reuse impact and offer detach behavior when canonical editing is unavailable.
- MSP-private and client-visible content must be visually unambiguous.
- New workflows include keyboard, responsive, loading, empty, error, and accessibility states.
- Interface copy for new controls and workflows comes from `src/i18n/en-US.json` through `translate()`, using stable semantic IDs and whole labels rather than assembled fragments. Existing literals migrate as each surface is hardened; `src/i18n/buttonLabels.test.ts` keeps migrated surfaces clean and stops the untranslated backlog growing.
- A control whose visible label can be hidden at any viewport carries an `aria-label` with the same string. `display: none` removes the label from the accessibility tree, so without it the control has no accessible name on the viewport where the label is hidden.
- Migrating copy is not rewording it. Changing a control's accessible name changes what the component and browser suites match on; reword deliberately and update those assertions in the same change.
- Follow the TekDocs design tokens and restrained application-shell patterns. Do not copy CollectZ source or assets and do not introduce decorative dashboard filler.
- List and table filters use the shared `src/FilterMenu.tsx` treatment: keep search visible, place filter dimensions in one filter-icon menu, use one disclosure submenu per dimension, show the active-filter count, and provide clear-all behavior. Do not add standalone filter selects to toolbars.

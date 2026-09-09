# UI foundations

This is the implementation contract for TekDocs application-shell and shared-control styling. It keeps route work consistent while the broader interface review in issue #60 continues.

## Shared values

| Purpose | Tokens | Values |
| --- | --- | --- |
| Spacing | `--space-1` through `--space-6` | 4, 8, 12, 16, 24, and 32 pixels |
| Corners | `--radius-small`, `--radius-control`, `--radius-panel` | 6, 7, and 8 pixels |
| Controls | `--control-compact-height`, `--control-height`, `--field-height`, `--icon-control-size` | 32, 36, 38, and 34 pixels |
| Shell | `--shell-height`, `--sidebar-width`, `--sidebar-collapsed-width`, `--content-width` | 60, 244, 68, and 1180 pixels |
| Elevation | `--shadow-popover`, `--shadow-sidebar-popover`, `--shadow-dialog` | Restrained shadows for overlays only |

## Rules

- Shared shell, button, field, panel, menu, and dialog rules use these tokens rather than introducing another near-equivalent value.
- Normal content hierarchy comes from typography, spacing, and borders. Do not add gradients, glow, glass effects, blur, oversized corner radii, or decorative cards to shared controls.
- Shadows communicate that a menu or dialog sits above the page. Static page sections do not need elevation.
- Controls keep visible labels when the action is not universally understood. Icon-only controls require an accessible name and a clear hover or focus treatment.
- Focus indicators, forced-colors support, reduced-motion behavior, mobile navigation, narrow-width layouts, and print behavior must remain intact.
- Intrinsic content dimensions, data visualizations, and genuinely route-specific layouts may use values outside this scale. Record recurring exceptions here instead of silently creating a second foundation.

## Create and edit surfaces

- New and edit workflows open in the shared bounded dialog unless the workflow needs the page itself, such as document editing or a multi-step import review.
- Dialog forms use a two-column grid by default, one column on narrow screens, and three columns only for dense, clearly grouped settings or stock provenance.
- The dialog header and action row remain visible when the form body scrolls. Primary and cancel actions stay together at the bottom of the form.
- Native checkboxes never inherit text-field dimensions. They use the shared accent and a consistent 16-pixel control.
- Page-level primary actions stay in the page header. Import, export, and bulk actions sit with the collection they affect.
- A capability uses the same user-facing noun in navigation, headings, actions, and empty states. Internal route and API names may remain stable for compatibility.

## Reviewed shared surfaces

The current foundation covers the application frame, workspace navigation, top bar, page headers, primary and secondary actions, content sections, searches, forms, dialogs, status messages, empty states, and filter menus. The issue #60 review now also covers create and edit treatments for organizations, people, sites, assets, licenses, networks, invoice settings, stock, custom fields, compliance frameworks, integrations, and contracts. Route-specific tables, status treatments, editors, and specialized workflows remain in the issue #60 inventory until their own interaction and browser review is complete.

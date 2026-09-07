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

## Reviewed shared surfaces

The current foundation covers the application frame, workspace navigation, top bar, page headers, primary and secondary actions, content sections, searches, forms, dialogs, status messages, empty states, and filter menus. Route-specific tables, status treatments, editors, and specialized workflows remain in the issue #60 inventory until their own interaction and browser review is complete.

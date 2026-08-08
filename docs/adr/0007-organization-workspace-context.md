# ADR 0007: Organization workspace context

- Status: Accepted
- Date: 2026-08-08

## Decision

Treat the MSP and each organization as selectable application workspaces. An organization record links to a stable, deep-linkable workspace route. The selected route controls navigation and supplies an explicit scope to reads and mutations, but never grants permission by itself.

Workspace context is URL-derived rather than stored as mutable server-session state. This keeps bookmarks and browser history meaningful, permits independent workspaces in separate tabs, and avoids one request silently changing another request's authorization context. APIs resolve every organization identifier through the authenticated tenant and central policy service. Create operations derive tenant and organization ownership from that authorized scope instead of accepting ownership fields from the browser.

The workspace switcher searches only organizations visible to the current user, includes a distinct parent-context return to the MSP workspace, and labels the active organization with all of its classifications. While a client workspace is active, discovery is restricted to organizations carrying the client classification; a multi-classified client remains eligible. MSP-context discovery may search all authorized classifications. Classification controls presentation capabilities: client workspaces expose client-owned knowledge and operations; vendor, manufacturer, and partner workspaces expose supplier contacts, products, and related knowledge as those domain families arrive. A multi-classified organization exposes the union of authorized capabilities without duplicating its identity.

Every sidebar destination is derived from the URL-selected workspace. Organization navigation uses only organization-prefixed routes, while MSP navigation uses only top-level MSP routes and may expose additional business, governance, and administration areas. `docs/INFORMATION_ARCHITECTURE.md` is the maintained navigation matrix.

Data from a previous workspace must be cleared before a new workspace loads. Breadcrumbs, page titles, empty/error states, search, exports, background jobs, and browser history must preserve the active scope. Hiding a navigation item is never an authorization control.

## Consequences

- Domain APIs and routes need a shared workspace-scope resolver and consistent MSP-versus-organization representation.
- Every domain slice must test list, detail, create, update, search, and background behavior across MSP, selected organization, a different organization, and a different tenant as applicable.
- Vendor/manufacturer/partner differences remain capability and relationship rules over one organization model; they do not become parallel organization tables.
- Product catalogs and their documentation remain supplier-owned templates. Assigning a product to a client creates a client-owned asset with provenance links rather than moving or duplicating the supplier identity.

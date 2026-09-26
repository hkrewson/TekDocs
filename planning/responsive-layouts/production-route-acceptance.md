# Production route refresh acceptance — 0.8.46

This Phase 8 checkpoint connects the responsive route inventory to the actual
production Nginx image. Every supported route is materialized into a concrete
path and refreshed directly through both a local published address and an HTTPS
proxy origin. Dynamic organization paths and wildcard fallbacks are included.

The ten broad workspace routes still awaiting technician acceptance also receive
focused record-state URLs for Assets, Documentation, Files, Networks, and
Contracts in both MSP and organization contexts. These requests verify that
query-addressed drawers, records, and sections reach the SPA entry document
without exposing the container's internal port.

The gate requires a 200 response, the exact built entry document, no `Location`
header, revalidation caching, and the production content-security policy. Hashed
assets retain immutable caching and missing chunks remain 404 responses. The
existing directory probe continues to require relative Nginx redirects.

Run `make test-frontend-routing`. The target builds the production frontend image
and starts an isolated disposable container without application data volumes.
The route list comes from `routes.json`, so a newly supported route automatically
joins this production refresh gate.

This checkpoint covers production-image routing and public-address preservation.
It does not claim authenticated workflow behavior, technician acceptance,
upgrade/recovery completion, deployment, or release approval.

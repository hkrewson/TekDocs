# Frontend refreshes and public addresses — 0.8.46

The frontend listens on internal port 8080; published Docker ports and HTTPS proxies define the browser-facing address. Nginx-generated redirects are relative (`absolute_redirect off`), so they preserve the browser's public scheme, host and port. This does not rewrite redirects produced by Django or change the application public-URL setting.

Both `/assets` and `/assets/` explicitly serve the revalidated SPA entry document. The route shares its name with the build-output directory; without this exception a direct refresh redirects `/assets` to an absolute internal-port URL and the trailing-slash directory cannot render the app. Exact route handling keeps `/assets/<hashed-file>` caching and missing-file 404 behavior intact. In-app navigation may hide this defect because it does not request the document again.

`make test-frontend-routing` builds the actual production frontend image and checks document refreshes with local and HTTPS-proxy headers, entry caching/security headers, hashed JavaScript caching, missing chunks, and a synthetic directory redirect. Its disposable container has no data volumes. The gate is included in `release-gate`.

Existing browsers may have cached the old permanent redirect. After updating the frontend image, use the correct public address in a fresh/private session to verify; clear cached redirects if the old browser session still rewrites the address. Production needs the updated frontend image; a local rebuild does not update a remote deployment. No database migration or version change is required.

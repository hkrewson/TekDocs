# CSP and COEP hardening

Status: phase 1 implemented; runtime validation pending. Owner: maintainer / #38.
This is the post-v0.9.19 security slice that begins remediation of the
release-bounded `TD-DAST-INLINE-STYLE` and `TD-DAST-COEP` exceptions. It does not change
authentication, authorization, database policy, publication formats, or production.

## Acceptance criteria

- The browser application CSP is identical at Nginx and Django. Phase 1 keeps the
  dependency compatibility allowance explicit; final acceptance requires
  `style-src 'self'` without `unsafe-inline`.
- Application source has no React style properties, DOM style mutation, or raw HTML
  injection. CI rejects their reintroduction.
- Sanitized Mermaid output remains downloadable and accessible, but renders as a
  same-document `data:` image so generated SVG styles are not inline page styles.
- Overlay scroll locking remains correct when overlays overlap.
- Nginx and direct Django responses emit exactly one effective
  `Cross-Origin-Embedder-Policy: require-corp` value. Nginx hides the upstream copy
  before applying its edge policy because duplicate COEP fields fail open.
- Login/navigation, bundled fonts, the same-origin PDF worker, diagram rendering,
  downloads, desktop browsers, and maintained mobile browsers pass without CSP or
  COEP console violations.
- Offline HTML exports retain their separate sandbox policy. Their inline export
  styles do not weaken the web application's policy.
- Mermaid, Milkdown and Cytoscape runtime styling is isolated, replaced, or removed
  before the application header drops `unsafe-inline`.

## Source disposition

Phase 1 removes TekDocs-owned page-level inline styling rather than replacing it
with a nonce. CSP nonces authorize `style` elements, not arbitrary style attributes,
and application code no longer needs either form. Dynamic zoom and hierarchy
indentation use bounded CSS classes. Mermaid renderer output is sanitized as before
and then encoded as an image resource instead of being injected into the application
DOM.

Static dependency review showed that Mermaid creates temporary style elements and
attributes while producing SVG, Milkdown reads/writes editor presentation, and
Cytoscape creates and sizes canvas layers with DOM styles. Enforcing
`style-src 'self'` before those paths are isolated would break supported diagrams,
editing, and relationship graphs. The compatibility allowance therefore remains in
phase 1; this is a documented blocker, not closure of `TD-DAST-INLINE-STYLE`.

COEP uses `require-corp`. All application subresources inventoried in this slice
are same-origin or `data:` resources; the latter are limited to diagram images and
their bundled font data. External documentation and integration links are top-level
navigations rather than embedded resources. This slice does not add
COOP and does not claim `crossOriginIsolated`; that would be a separate auth and
window-lifecycle decision.

The behavior follows [CSP Level 3](https://www.w3.org/TR/CSP3/) and the
[WHATWG HTML COEP processing model](https://html.spec.whatwg.org/multipage/browsers.html#coep).

## Validation ledger

Verified statically:

- Nginx and Django policies agree, and the remaining `unsafe-inline` allowance is
  attributable to known dependency runtime behavior rather than first-party source.
- application TypeScript/TSX contains no inline style property, DOM style mutation,
  or `dangerouslySetInnerHTML` use;
- the first-party CSS needed to replace those runtime styles remains within a
  narrowly rebased 25 KiB compressed shell budget;
- PDF worker, fonts, API calls, downloads, and application bundles resolve from the
  application origin; and
- the existing standalone export CSP remains unchanged.

Needs validation on the exact source commit:

- frontend lint, typecheck, unit coverage, and production build;
- backend health/security-header tests;
- production-image routing/header rehearsal, including the proxied API path;
- Chromium, Firefox, WebKit, mobile Chromium, and mobile WebKit browser acceptance;
- guided/saved Mermaid diagrams, SVG download, PDF worker rendering, authentication
  navigation, fonts, and a check for CSP/COEP console violations; and
- passive DAST confirming that ZAP 10055-6 and 90004-2 are retired rather than
  suppressed. Phase 1 is expected to retire 90004-2 only; 10055-6 remains open until
  the dependency isolation criterion is complete.

The requested security-audit workflow requires target-controlled execution to run
with OS-enforced network, environment, filesystem, and resource isolation. That
sandbox is not available in this development checkout, and the repository rules
also prohibit creating a parallel local test stack. Hosted CI must therefore supply
the runtime evidence; no production endpoint was probed.

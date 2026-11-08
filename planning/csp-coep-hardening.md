# CSP and COEP hardening

Status: complete; exact-source hosted validation passed. Owner: maintainer / #38.
This post-v0.9.19 security slice completes remediation of the
release-bounded `TD-DAST-INLINE-STYLE` and `TD-DAST-COEP` exceptions. It does not change
authentication, authorization, database policy, publication formats, or production.

## Acceptance criteria

- The browser application CSP is identical at Nginx and Django and enforces
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
  downloads, desktop browsers, and maintained mobile browsers pass without
  unexpected CSP or COEP violations. WebKit's exact blocked transient editor
  attempt remains observable and bounded until the browser no longer emits it.
- Offline HTML exports retain their separate sandbox policy. Their inline export
  styles do not weaken the web application's policy.
- Mermaid, Milkdown and Cytoscape runtime styling remains isolated, replaced, or
  absent while the strict application header is enforced.

## Source disposition

Phase 1 removes TekDocs-owned page-level inline styling rather than replacing it
with a nonce. CSP nonces authorize `style` elements, not arbitrary style attributes,
and application code no longer needs either form. Dynamic zoom and hierarchy
indentation use bounded CSS classes. Mermaid renderer output is sanitized as before
and then encoded as an image resource instead of being injected into the application
DOM.

Enforced browser reproductions refined the earlier static dependency inventory.
Cytoscape produced one `style-src-elem` violation solely to add its private
container `position: relative` rule; TekDocs now supplies that rule in external CSS
and a checked document sentinel prevents the dependency injection. Mermaid was the
remaining verified renderer blocker: a real in-page preview request created
temporary style elements and many style attributes while producing the SVG. Phase 2
moves preview generation behind the existing isolated renderer boundary. The browser
receives sanitized SVG and displays it only as a `data:` image, with client-side
sanitization retained as defense in depth.

Hosted WebKit then exposed a separate Milkdown mount behavior. Its optional cursor
feature left inline-style helpers in the document, so TekDocs disables that feature.
WebKit's editor engine also attempts `text-overflow:inherit` on transient internal
nodes. The enforced policy blocks those attempts and no inline style reaches the
document. `report-sample` makes the exact blocked declaration observable; acceptance
allows only that exact WebKit event and continues to fail on every other CSP event or
persisted style attribute. The application policy remains `style-src 'self'` without
an inline-style exception.

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

- Nginx and Django policies agree on `style-src 'self'` without an inline-style
  exception and include `report-sample` for rejected style diagnostics.
- application TypeScript/TSX contains no inline style property, DOM style mutation,
  or `dangerouslySetInnerHTML` use;
- the first-party CSS needed to replace those runtime styles remains within a
  narrowly rebased 25 KiB compressed shell budget;
- PDF worker, fonts, API calls, downloads, and application bundles resolve from the
  application origin; and
- the existing standalone export CSP remains unchanged.

Verified locally on the phase 2 candidate:

- frontend typecheck and production build, including bundle budgets;
- focused Mermaid component/API unit tests, lint, and the fail-closed CSP source
  check;
- focused backend diagram-preview and security-header tests;
- production-image headers for the application and proxied API paths; and
- the real guided/saved Mermaid diagram path in Chrome under enforced
  `style-src 'self'`, with no CSP or COEP console violations;
- the exact guided/saved diagram regression in Chromium, Firefox and WebKit; WebKit
  reports only its blocked `text-overflow:inherit` editor attempts, while the page
  retains no inline style attributes;
- the Django liveness security-header contract against the retained isolated test
  database; and
- the production-shaped Nginx response, which retains strict style blocking and
  emits `Cross-Origin-Embedder-Policy: require-corp`.

Verified in hosted validation on exact source `286e84a309098dae19c50fc45511dcf3bf39678b`:

- Build [42439813889](https://github.com/hkrewson/TekDocs/actions/runs/42439813889)
  passed the complete source, production-image, routing, dependency, license, secret,
  vulnerability and final validation gates;
- CodeQL [42449387473](https://github.com/hkrewson/TekDocs/actions/runs/42449387473)
  passed the Python and JavaScript/TypeScript extended security-and-quality queries
  and published commit-bound evidence;
- Extended validation
  [42449370137](https://github.com/hkrewson/TekDocs/actions/runs/42449370137)
  passed Chromium, Firefox, WebKit, mobile Chromium and mobile WebKit, supported
  upgrades, encrypted recovery, performance and commit-bound evidence delivery; and
- the same Extended run's production-shaped passive DAST passed CSP rule 10055 with
  no inline-style finding and no missing-COEP subfinding. ZAP still reports its
  distinct missing-COOP warning under rule 90004; COOP and a claim of full
  cross-origin isolation are explicitly outside this slice.

`TD-DAST-INLINE-STYLE` and `TD-DAST-COEP` are therefore retired on November 8,
2026. Historical candidate records remain unchanged because they accurately record
the policy shipped in those releases. Issue #38 remains open for the broader 1.0
automated-security-assurance acceptance criteria.

Hosted Build 42326080728 reproduced 54 stale browser assertions that still inspected
the removed inline scroll style and one Mermaid `font-src:data` violation. Build
42342001747 confirmed those corrections: the font violation and the original 54
failures were gone, 394 Chromium cases passed, and 18 cases exposed three remaining
copies of the same inline-style assertion across six viewport widths. The follow-up
uses the lock class plus computed overflow everywhere; exact-source hosted browser
evidence remains pending.

Build 42377423789 then cleared the Chromium regression and reached the production
image gate. Its Mailpit scan discovered unsuppressed HIGH CVE-2026-78661 in
`golang.org/x/net` v0.61.0, fixed in v0.62.0. The bounded follow-up retains the
pinned Mailpit source, overlays only that fixed module version, and asserts the
compiled dependency identity before hosted scanning.

Build 42382239045 passed the exact Mailpit follow-up, including Chromium,
production images, the unsuppressed vulnerability scan and final validation.
On November 7, a local enforced `style-src 'self'` reproduction then exercised
actual Milkdown authoring, Mermaid preview and a two-node Cytoscape graph against
the production-shaped frontend. Milkdown emitted no violation. Cytoscape emitted
one inline style-element violation, traced to its fixed private container rule;
the external-rule/sentinel correction removes that injection and its source gate
fails closed if the dependency contract changes. A real Mermaid preview emitted
both style-element and style-attribute violations. Phase 2 moves Mermaid preview
rendering behind the existing isolated renderer boundary and removes `unsafe-inline`
from both application policies. The repeated production-image Chrome path completed
without a CSP or COEP violation. The hosted browser matrix and passive DAST must
still confirm the stricter policy.

Exact-source Extended CI run 42428229995 passed Chromium and Firefox but WebKit
reported sixteen blocked `style-src-attr` events while opening the Milkdown editor.
The failure was reproduced locally under WebKit with the production-shaped header.
Disabling Milkdown's optional cursor feature removed its persistent inline-style
helpers. CSP `report-sample` identified the remaining transient browser attempts as
`text-overflow:inherit`; they are blocked by the strict policy and leave no style
attribute in the document. The focused three-browser regression now passes locally.
Hosted Extended CI and passive DAST subsequently passed as recorded above.

The requested security-audit workflow requires target-controlled execution to run
with OS-enforced network, environment, filesystem, and resource isolation. That
sandbox is not available in this development checkout, and the repository rules
also prohibit creating a parallel local test stack. Hosted CI must therefore supply
the runtime evidence; no production endpoint was probed.

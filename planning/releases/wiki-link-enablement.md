# Published Wiki links in contextual Help

## Scope and acceptance

Post-0.9.8 application slice: expose the guide for the active route after Wiki
publication and public verification. Links must retain their exact approved
Wiki destinations, separate-tab/referrer protections, local summaries, responsive
layout, keyboard containment and Escape/focus return. No migration or API change.

The public prerequisite is Wiki commit
`dec75e1e91b5da35458809e05de75cef3da48d07`, with all 46 content pages and 25
contextual targets verified in `0.9.8-wiki-publication-verification.json`.

## Implementation

- Enable WIKI_PUBLISHED and retain the existing translated guide action.
- Update component, shell and responsive browser assertions for the guide link,
  exact destination, target/rel attributes and absence of the unpublished status.
- Explicitly move Tab/Shift+Tab from non-tabbable initial overlay focus to the
  first/last eligible control. Existing endpoint wrapping remains intact.

## Reproduction and qualifications

An initial browser run reused an existing server on port 3200 and saw the old
unpublished state. Validation moved to a fresh production frontend image on an
isolated loopback port, with mocked API data and no production services involved.
The initial image run reproduced obsolete heading-focus expectations. After
asserting intended link traversal, WebKit still skipped the link on first Tab.
The shared focus trap had delegated initial non-tabbable heading traversal to
browser defaults; the explicit transition fixes that reproduced failure.

The first complete frontend suite passed 770 tests and failed the obsolete App
unpublished-state assertion plus one Stock off-page Edit lookup. The App assertion
now checks the published destination. Stock code and assertions were unchanged;
its focused retry passed, but the original cause remains unknown. The failure
ledger retains these observations rather than claiming the first run passed.

## Validation

The complete unit rerun passed 772 tests across 127 files. Its subsequent lint
step found the disposable browser configuration outside the TypeScript project;
that temporary file was removed and the full gate restarted. The focused Help/topics/Stock
suite passed all 11 tests. The published Wiki snapshot passed its 37 required-page
inventory and local-link check. Browser validation uses the actual production
frontend Docker image with API fixtures; this does not claim a new backend or
full production acceptance run.

## Release boundary

This changes application source after frozen v0.9.8 commit 05abb13. It does not
change that tag, its images, its candidate manifest, or the deployed installation.
A future candidate must receive its own required hosted/release validation and
risk decisions before publication/deployment. The existing 05abb13 security
acceptance must not be transferred to this runtime change.


Final-source production frontend image:
`sha256:c21e800d11771b81002ceac7db4026a20c29efa1f77336fbb28b37f297f34732`.
Its health check passed. All 24 focused browser cases passed against this image
across Chromium, Firefox and WebKit, including six widths from 320 to 1440 pixels,
exact guide URLs, safe link attributes, focus containment, return focus and axe
checks. This is local Docker evidence, not a registry publication.


Final clean `make check-frontend` passed: 127 test files / 772 tests, coverage
thresholds, OpenAPI drift, lint, TypeScript, production build and bundle budgets.
The unchanged Stock case passed in both complete reruns; its initial failure is
retained with unknown cause. `git diff --check` passed. No hosted validation or
new release is claimed by these local results.

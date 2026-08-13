# ADR 0084: Public Wiki and contextual help boundary

- Status: Accepted locally for `0.8.8`; external publication blocked
- Date: 2026-08-13

## Decision

The public GitHub Wiki is the one end-user and operator manual. TekDocs will not add a second manual below the repository `docs/` tree. Repository documents remain the reviewed engineering, security, architecture, runbook, and release sources used to write and verify the public corpus.

`.github/wiki-pages.json` freezes public page slugs, audience coverage, contextual-help membership, and the source evidence that must be reviewed for each page. `scripts/check-documentation.py` checks source existence, relative links, slug safety and uniqueness, audience coverage, and exact drift between the manifest and the application. When given a separately cloned Wiki checkout, it also requires every declared page and validates its local links. It never publishes.

Authenticated pages display a concise, bundled help summary selected from the route's logical workspace area. Organization and MSP versions of an area resolve to the same topic. The application does not fetch, render, or execute Wiki content. A full-guide link is enabled only after the public corpus exists and its checkout passes the documentation contract.

The intended public URL is `https://github.com/hkrewson/TekDocs/wiki`. It does not currently exist, this checkout has no remote, and project policy prohibits external publication without explicit authorization. `WIKI_PUBLISHED` therefore remains false and the UI states that publication is pending rather than emitting broken links.

## Consequences

- Help remains useful and safe inside an authenticated page when GitHub is unavailable.
- Stable slugs can be checked before an external publication operation is authorized.
- Wiki content can evolve independently, but removing a linked slug requires a compatibility page or application update.
- `0.8.8` cannot be certified until the real Wiki repository exists, contains the complete reviewed corpus, passes the checkout gate, is publicly reachable, and the application link flag is enabled and browser-tested.

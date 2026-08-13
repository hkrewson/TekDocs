# Localization and time contract

TekDocs `0.8.4` is localization-ready but ships only an English (`en-US`) catalog. Readiness means new interface copy and locale-sensitive presentation have one maintained extension seam; it does not mean an unreviewed machine translation is available.

## Data contract

- API timestamps are offset-aware ISO 8601 instants. UTC is the storage and default server runtime zone. A timestamp without `Z` or a numeric offset is ambiguous and the frontend formatter rejects it.
- Calendar dates such as expiration or acquisition dates remain `YYYY-MM-DD` plain dates. They are formatted in a fixed UTC calendar so a browser west of UTC cannot display the prior day.
- An IANA time-zone name is required wherever civil time affects behavior. Production startup rejects invalid `TZ`; notification preferences retain their own validated IANA zone because delivery semantics must not depend on the host setting.
- The browser displays instants in its current IANA zone unless a workflow has an explicit saved zone. Formatting must use `src/i18n/localization.ts`, not ad hoc `Date` locale methods.
- Domain identifiers, UUIDs, checksums, CIDRs, IP/MAC values, serials, product model numbers, money source values, Markdown, and signed manifests are never localized in storage or signatures.

## Message contract

- `src/i18n/en-US.json` is the initial catalog. Stable semantic IDs are preferable to using English source text as identity.
- `translate()` performs typed catalog lookup and named substitution. Variable values are data, never message IDs or HTML.
- Locale negotiation may select only a catalog actually shipped by TekDocs. Unknown or malformed browser hints fall back to `en-US`.
- The document root publishes the active BCP 47 language and writing direction. A future right-to-left catalog must add its direction and browser/reflow evidence before release.
- Plural, gender, date, number, currency, and list grammar must use `Intl` or a deliberately reviewed ICU-compatible message layer. Do not assemble translated sentences from fragments.
- User-authored organization names, documents, labels, and external provider values are content and are not translated by the interface catalog.

## Adding a locale

1. Add a complete reviewed catalog with the exact key set and record its BCP 47 tag in `supportedLocales`.
2. Add locale negotiation, fallback, direction, plural, long-label reflow, input, sorting, and date/number snapshots.
3. Review every server email, PDF, notification, accessibility name, error, and contextual-help link for the new locale.
4. Verify that no localized display value enters canonical Markdown, signed manifests, API machine fields, audit identifiers, or integration fingerprints.
5. Run component, browser, accessibility, mail, PDF, and upgrade gates before advertising support.

Existing feature copy will migrate into stable catalog IDs as each surface is hardened. New shared controls and new workflows must use the catalog immediately; broad search-and-replace translation without product review is prohibited.

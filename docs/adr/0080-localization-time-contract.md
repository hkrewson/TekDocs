# ADR 0080: Locale is presentation; time semantics are explicit

Date: 2026-08-13

Status: Accepted for `0.8.4`

## Decision

TekDocs stores instants as timezone-aware values and runs servers in UTC by default. Civil scheduling stores a validated IANA zone at the domain boundary that needs it. Date-only values remain calendar dates and must not be parsed as local-midnight instants.

The browser owns locale-sensitive presentation through one typed localization module and one catalog registry. It accepts only shipped BCP 47 locales, publishes language/direction on the document root, formats instants, dates, hours, and integers through `Intl`, and rejects offset-free timestamps. `en-US` is the only shipped catalog in this release; readiness is not represented as translation coverage.

## Consequences

Machine identifiers, canonical Markdown, signed artifacts, APIs, audit codes, and integration fingerprints remain locale-neutral. A future locale must provide a complete reviewed catalog, direction/plural behavior, long-label and assistive-technology evidence, and mail/PDF coverage. Existing surface copy migrates incrementally, while new shared components and workflows use stable message IDs from their first implementation.

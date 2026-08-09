# ADR 0019: Markdown dialect, rendering, and help ownership

- Status: Accepted for `0.2.1`
- Date: 2026-08-09

## Decision

TekDocs stores canonical CommonMark-compatible Markdown with a deliberately small technical-documentation extension set. The supported contract is headings one through six, emphasis, strong emphasis, strikethrough, links, ordered and unordered lists, task lists, blockquotes, tables with alignment, fenced and inline code, horizontal rules, footnotes, managed attachments when that domain arrives, stable `tekdocs://entity/{uuid}` links, semantic highlight, and typed callouts.

Semantic highlight serializes as `==text==` and renders as `<mark>`. It means “pay attention to or verify this passage”; it is not an author-selected color. Callouts serialize as blockquotes beginning with `[!NOTE]`, `[!TIP]`, `[!IMPORTANT]`, `[!WARNING]`, or `[!CAUTION]`. Their application-controlled presentation conveys the callout type through text, structure, iconography, and color rather than color alone. Arbitrary text/background colors, raw HTML, MDX, scripts, inline styles, and author-supplied CSS are outside the dialect.

Milkdown remains the visual editor because its model reads and emits Markdown. The fixed round-trip corpus combines a realistic UniFi network guide with every supported extension. A release may not claim editor compatibility when the corpus loses meaning during Markdown-to-editor-to-Markdown conversion. Visual editing provides a persistent structural toolbar, a contextual inline toolbar, raw source, and preview; stored editor HTML or JSON is never authoritative.

Preview is rendered by the authenticated Django API under `documents.view`. The server disables raw HTML, renders through `markdown-it-py` plus reviewed transforms, and applies an explicit `nh3` tag, attribute, and URL-scheme allowlist. The browser then applies a second explicit DOMPurify allowlist before the one centralized HTML sink. Client sanitization is defense in depth and never substitutes for the server boundary. Rendering requests are size-bounded and use the normal same-origin session/CSRF contract.

End-user and operator documentation will be published in the public repository's actual GitHub Wiki after repository publication is authorized. The repository `docs/` tree remains for engineering decisions, security contracts, runbooks, and release evidence—not a duplicate end-user manual. Until then, the editor's Formatting help page is the internally hosted user reference. The supported dialect, fixture assertions, in-app help, and Wiki must agree at release closeout. Later contextual help may surface a concise page-specific summary and a stable Wiki link; it must not load executable remote content into an authenticated page.

## Consequences

- A familiar toolbar can grow without creating a proprietary storage format.
- Highlight and callouts improve technical scanning while retaining readable source and reasonable portability to other Markdown tools.
- Authors cannot choose arbitrary CSS or colors. New semantic presentation requires a reviewed Markdown extension, accessibility behavior, round-trip coverage, server renderer rule, sanitizer update, and malicious-corpus case.
- Escaped unsafe source may remain visible as literal text, but cannot become authored DOM, active URLs, styles, or event handlers.
- Actual GitHub Wiki publishing and contextual-help links remain future work because this slice is not authorized to publish externally and the product's stable page taxonomy is still evolving.

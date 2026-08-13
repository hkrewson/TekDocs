# Accessibility contract

TekDocs targets WCAG 2.2 Level AA for authentication, navigation, documentation editing and publication, client portal, inventory, monitoring, and administrative workflows. This is an engineering conformance target, not a claim of independent certification.

## Required behavior

- Pages expose one descriptive title, one primary `main` landmark, ordered headings, labelled form controls, named status/error regions, and semantic tables or lists.
- The first keyboard stop in the authenticated shell is a visible “Skip to main content” link. Client-side route changes move focus to the new main region without stealing focus on initial load.
- Menus, dialogs, workspace switching, editor tabs, pagination, and disclosure controls work without a pointer. Composite tabs use one tab stop plus Left/Right/Home/End movement; Escape closes transient menus and returns focus to their trigger.
- Focus remains visible and unobscured. Controls retain a minimum 24 by 24 CSS-pixel target unless the WCAG inline/spacing exceptions apply.
- Text and meaningful UI components meet AA contrast. Color is never the only indicator of Workspace, privacy, state, error, or selection.
- Layout reflows at 320 CSS pixels and remains usable at 200% text zoom. Content may scroll where the content itself is two-dimensional, such as a wide comparison table.
- Motion is nonessential. `prefers-reduced-motion` removes transitions and repeating animation. Active navigation and editor state remain discernible in forced-colors mode.
- Stored Markdown and publication content are rendered through the existing sanitization boundary. Accessibility metadata may be derived for presentation, but editor HTML never becomes canonical.
- Validation identifies the field, explains the correction in text, and preserves user-entered non-secret values when safe. Authentication errors remain non-enumerating.

## Verification

Every pull request runs frontend component tests and Chromium Playwright smoke. Critical shell, authentication, editor, revision-history, workspace, portal, and administrative surfaces use axe; the `0.8.3` critical checks explicitly select WCAG 2.0 A/AA, 2.1 A/AA, and 2.2 AA rules. Automated analysis cannot prove full conformance, so milestone and release-candidate reviews also exercise:

1. keyboard-only entry, completion, cancellation, error recovery, and focus return;
2. VoiceOver name, role, state, landmark, heading, table, and live-region output;
3. 320-pixel reflow, 200% text zoom, and text-spacing overrides;
4. reduced motion, increased contrast, and forced colors;
5. session timeout, MFA, destructive confirmation, editor, publication, and portal boundaries.

Firefox and WebKit are blocking at `0.8.6`; an external review remains `0.8.9`, and final remediation evidence remains `0.9.5`. A new privileged or client-facing workflow must add keyboard and automated negative coverage before it can inherit this contract.

## Known limits

- Generated PDFs must retain readable structure and text, but PDF/UA certification is not claimed.
- Third-party browser extensions, operating-system assistive technology defects, and user-authored linked resources are outside the application boundary.
- Rich Markdown content can still be authored with poor heading hierarchy or link wording. TekDocs provides semantic controls and safe output; later contextual guidance should help authors improve content quality without silently rewriting canonical Markdown.

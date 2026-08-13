# ADR 0079: Accessibility is a release contract

Date: 2026-08-13

Status: Accepted for `0.8.3`

## Decision

TekDocs targets WCAG 2.2 Level AA across its critical workflows. Accessibility is treated as application behavior: routing owns predictable main-region focus, the shell owns bypass navigation, composite widgets own documented keyboard interaction and focus return, and visual states must survive reduced-motion and forced-colors preferences.

Automated axe analysis, component tests, and Playwright keyboard assertions are blocking regression evidence, but are not represented as complete or external certification. Manual keyboard, VoiceOver, reflow, zoom, text-spacing, contrast-mode, timeout, and error-recovery review remains required at release boundaries. Browser-engine certification is separately owned by `0.8.6`; external review is owned by `0.8.9`.

## Consequences

New workflows must expose semantic names, roles, states, errors, focus order, keyboard completion, responsive behavior, and accessible denial paths. Hiding a privileged control never substitutes for server authorization. Route-focus behavior may not steal the initial browser focus from the skip link, and editor enhancements may not replace standard tab behavior with an undocumented keyboard model.

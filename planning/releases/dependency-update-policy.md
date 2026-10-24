# Dependency update policy — October 24, 2026

Scope: triage the dependency PR failures after the 0.9.12 main push. Keep routine
updates useful without treating a major toolchain change as an automatic patch.
Acceptance: compatible routine grouping, explicit coordinated-update boundaries,
unchanged runtime pins and unchanged security/renderer gates.

## Observed failures

- PR 91 / Build 40056145238: npm refuses TypeScript 7.0.2 because
  openapi-typescript 7.13.0 requires TypeScript 5. Both failed jobs report this
  same install conflict. Keep TypeScript majors under manual compatibility review.
- PR 115 / Build 40055976387: changing only the frontend Node image to 26 breaks
  the browser image's exact Node 24.22.1 assertion. Coordinate all Node images,
  browser tooling, engine declarations and assertions when changing versions.
- PR 116 / Build 40056011665 and PR 118 / Build 40056064222: separate renderer
  and frontend upgrades select Mermaid 12.2.0 on only one side. The unchanged
  contract rejects the 11.16.1/12.2.0 mismatch. PR 118 was reproduced from its
  actual manifests/locks in an isolated temporary directory before policy edits.

These are incompatible proposed upgrades, not failures of published 0.9.12.
No failed PR is merged or silently marked fixed by editing update policy.

## Policy

Routine Python and npm production/development groups contain minor/patch updates.
Other major upgrades remain separate proposals. Mermaid, Mermaid CLI and
Puppeteer are excluded from routine groups and are individually visible for
coordinated review; separate proposals must not be merged independently.
Node major and TypeScript major updates are explicitly manual while their current
cross-image/API-generator compatibility requirements remain. Security advisories
still require active triage; ignores are not a finding disposition.

The maintainer owns coordinated updates. Reconsider the Node/TypeScript constraints
at the next runtime candidate or November 12, 2026, whichever is earlier. Do not
use force/legacy peer installation or weaken version assertions to merge a PR.
Existing PRs may need replacement after the policy is published; unchanged old
red runs remain historical evidence.

Reference: [GitHub Dependabot options](https://docs.github.com/en/code-security/reference/supply-chain-security/dependabot-options-reference).

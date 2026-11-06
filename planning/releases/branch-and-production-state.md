# Branch and production state

## Acceptance

TekDocs must have one unambiguous development line, immutable release identity,
an auditable production pointer and no branch whose moving head is mistaken for
the deployed application. Repository rules and operator tooling must enforce the
same model.

## Development state

`main` is the active development and integration line. It is not production.
The `Protect main delivery` repository ruleset blocks deletion and force pushes.
Changes from anyone other than the named maintainer must arrive through a pull
request, have one approval, resolve review threads and pass the stable
`Validation passed` check against the current `main` baseline. The maintainer has
an explicit, audited bypass so reviewed direct-main delivery and the single-push
release workflow remain possible.

There is no long-lived `dev` branch. Feature or dependency branches are temporary
review surfaces and do not define an environment.

## Release state

A deployable release exists only when both immutable Git references exist:

- `vMAJOR.MINOR.PATCH` identifies the reviewed application commit. Future tags
  are annotated with a short committed summary and explicit breaking-change
  disposition; historical lightweight tags remain valid and immutable;
- `receipts/vMAJOR.MINOR.PATCH` identifies the CI-created receipt commit whose
  sole parent is that application commit and whose only change is the reviewed
  image receipt.

The receipt binds the backend, frontend, renderer and Mailpit image digests.
Annotation text is an operator catalog aid, not deployment authority; the updater
still peels the tag and validates the companion receipt and immutable images.
Passing CI on a later `main` commit does not move or replace an existing release.
There is no moving `production` branch and no rule that production stays one
commit or one version behind. Commit distance is not a safety or soak measure.

## Production state

Production runs one selected release by immutable image digest. Its `.env`
records `TEKDOCS_DEPLOYED_COMMIT` and the four deployed digests only after
migration, readiness and running-image verification succeed. Those recorded
values, the application tag and the receipt are the production identity; the
tooling checkout may be a newer clean commit because release mode uses the tagged
Compose files without moving the checkout during deployment.

The supported unattended path is a fixed maintenance window running
`TEKDOCS_MINIMUM_RELEASE_AGE_HOURS=48 scripts/update-production.sh --latest`.
The updater must first validate the
latest application/receipt pair and must exit without backup or Docker activity
when that exact release is already recorded as deployed or has not completed the
configured soak window. It never falls back to an older release. An explicit
operator-directed `--release` is not delayed by the unattended soak policy.
Every real update keeps
the existing encrypted-backup, forward-ancestry, migration, readiness and image
identity gates. A failed run remains failed and requires operator review; it does
not fall back to an older or unverified release.

## Security automation

Dependabot vulnerability alerts and security-update pull requests are enabled.
There is no blanket dependency auto-merge. A narrowly scoped update may receive
per-PR auto-merge only after its advisory versions, lockfiles, repository-specific
coordination rules and required checks are reviewed. Coordinated families such as
Mermaid, Mermaid CLI and Puppeteer move together. Major upgrades and stale or
incomplete hash-lock changes remain blocked for a manual slice.

CodeQL reports findings; it does not accept or rewrite application code. High and
medium security findings require explicit triage, a tested fix or a documented
disposition. Green workflow execution is evidence, not automatic risk acceptance.

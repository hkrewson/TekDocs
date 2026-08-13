# GitHub Wiki publication contract

TekDocs end-user and operator documentation belongs in the public repository's actual GitHub Wiki. The repository `docs/` tree remains the reviewed engineering, security, architecture, and operational source record; it is not presented as a second user manual.

## Current status

Publication is blocked. This checkout has no Git remote, and `https://github.com/hkrewson/TekDocs` and its Wiki do not currently exist publicly. The application therefore displays page-specific local help but does not expose broken external links. `frontend/src/help/topics.ts` must keep `WIKI_PUBLISHED` false until the published corpus passes this contract.

## Page contract

`.github/wiki-pages.json` owns stable Wiki slugs, audience coverage, contextual-help membership, and the reviewed repository sources from which each public page must be written. It contains no duplicate manual. `scripts/check-documentation.py` blocks missing sources, unsafe or missing local links, audience gaps, duplicate/unsafe slugs, and drift between public page slugs and application help.

The corpus must cover four distinct audiences:

- end users performing workspace, documentation, inventory, monitoring, and compliance tasks;
- operators installing, configuring, backing up, restoring, upgrading, and troubleshooting an installation;
- security reviewers evaluating authentication, authorization, isolation, secret custody, egress, and recovery boundaries;
- API consumers using `/api/v1`, OpenAPI, scoped tokens, idempotency, webhooks, and integrations.

## Authorized publication procedure

Publication changes external state and must be separately authorized.

1. Create the public repository, enable its Wiki, and configure this application's origin remote.
2. Clone the Wiki Git repository into a separate checkout ending in `.wiki`; never place the manual under this repository's `docs/` tree.
3. Write the complete pages listed in `.github/wiki-pages.json`. Public prose must describe the shipped behavior and must not contain credentials, customer data, internal paths, test identities, unpublished findings, or deployment-specific values.
4. Run `python3 scripts/check-documentation.py --wiki-checkout /absolute/path/to/TekDocs.wiki`.
5. Review all outbound links and screenshots manually. Screenshots must contain synthetic data and must not expose browser storage, notifications, local paths, or security tokens.
6. Commit and push the Wiki only after explicit authorization. Record its exact commit in the `0.8.8` release evidence.
7. Change `WIKI_PUBLISHED` to true, run `make documentation-check`, test every contextual link against the public Wiki, and complete the production/browser gates.

Wiki edits after release must update the page manifest or reviewed source when behavior changes. A page title may change, but a published slug used by contextual help must remain as a redirect or retained compatibility page.

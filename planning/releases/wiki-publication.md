# GitHub Wiki publication contract

The public GitHub Wiki is TekDocs' user and operator manual. Repository `docs/`
files remain engineering and operational source records, not a second user manual.

## Current status

The repository and Wiki exist publicly. The public Wiki is incomplete against
`.github/wiki-pages.json`. The local sibling Wiki checkout contains candidate
page drafts, including the missing task and operator pages, but these have not
been published. Consult the current release follow-up record for verification.

`frontend/src/help/topics.ts` keeps `WIKI_PUBLISHED` false. The application uses
local contextual help and does not enable external Wiki links until publication
and public-link verification are complete. A locally passing inventory does not
justify switching that flag.

## Page contract

`.github/wiki-pages.json` owns the 37 required slugs, audiences and contextual-help
membership. `scripts/check-wiki.py` validates that inventory against application
help. With `--checkout`, it also requires all pages and checks local page links,
including supplemental operator pages and the sidebar.

Pages should be written from current reviewed implementation and engineering
sources, distinguish present behavior from planned compatibility, and give users
a useful task workflow and its limitations. Candidate drafts link to their source
revision. An inventory/link pass is not proof of factual completeness or usability.

## Publication procedure

1. Use the separate Wiki Git checkout; preserve unrelated local edits.
2. Review every required page against the intended application candidate. Keep
   customer data, credentials, private diagnostics and deployment-specific values
   out of prose and screenshots.
3. Run `python3 scripts/check-wiki.py --checkout /absolute/path/to/TekDocs.wiki`.
4. Review local and outbound links. Confirm that release and security pages do not
   claim approval, publication, assurance or deployment that has not occurred.
5. Obtain explicit authorization before pushing the Wiki. Record the exact Wiki
   commit and its published page checks in release evidence.
6. Verify the complete public corpus and every contextual target. Only then make
   a separately reviewed application change enabling `WIKI_PUBLISHED`, with its
   applicable frontend and browser gates.

A slug used by contextual help must remain available if its display title changes.
Wiki publication, application-link enablement and deployment are distinct steps.

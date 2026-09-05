# Diagram renderer maintenance

TekDocs uses the same Mermaid runtime for the editor preview and the isolated export renderer. The renderer also depends on Mermaid CLI, Puppeteer, and Alpine Chromium. Treat those four parts as one compatibility unit: a change to any one of them requires the complete diagram gate.

## Contract

- `frontend/package.json` pins Mermaid to an exact version.
- `renderer/package.json` pins Mermaid CLI and Puppeteer to exact versions.
- Both lockfiles must agree with their manifests.
- The Mermaid version resolved by the renderer must exactly match the frontend Mermaid version. This prevents a saved diagram from previewing one way and exporting another.
- `renderer/Dockerfile` pins its Node base image by digest. `CHROMIUM_SERIES` records the reviewed Alpine Chromium major version, the image build rejects a different series, and the installed version is retained in `/chromium-version`.
- Dependabot reports frontend Mermaid, renderer npm, and renderer container updates. It does not authorize or merge them.

Run the fast contract check with:

```sh
make check-renderer-dependency-contract
```

CI retains `renderer-dependency-contract.json`, which records the effective versions and SHA-256 hashes of every file that controls rendering. The record is deterministic and contains no timestamp or secret.

## Updating the renderer

Use this sequence for any Mermaid, Mermaid CLI, Puppeteer, Chromium, renderer configuration, or renderer base-image change.

1. Start from a clean branch at the candidate commit. Do not combine the update with unrelated feature work.
2. Use the repository-supported Node 24 toolchain. Older npm releases cannot read the current lockfile reliably.
3. Update packages with npm so both manifests and lockfiles are generated together. Never edit a lockfile by hand.
4. Read `renderer/package-lock.json` to find the exact `node_modules/mermaid` version selected by Mermaid CLI. Set the frontend `mermaid` dependency to that exact version and regenerate the frontend lockfile.
5. If the renderer image installs a new Chromium major, change `CHROMIUM_SERIES` to that major. Do not loosen or remove the image-build assertion.
6. Run `make check-renderer-dependency-contract`. A mismatch is a blocked update, not a warning to waive.
7. Run the renderer npm production audit and license check:

   ```sh
   npm --prefix renderer ci --omit=dev --no-audit --no-fund
   npm --prefix renderer audit --omit=dev --audit-level=high
   node renderer/check-licenses.mjs
   ```

8. Run `make test-diagram-exports`. It must cover every supported diagram family, unsupported-family handling, unsafe source, accessible fallbacks, static publication, and all export formats.
9. Run `make production-image-rehearsal`. Confirm that the runtime browser matches `/chromium-version`, the renderer works without network access, and the production-shaped application exports a real diagram.
10. Run the Chromium browser regression and the live browser-to-PostgreSQL journey. An editor-only preview is not enough evidence.
11. Review representative flowchart, sequence, class, state, and entity-relationship diagrams in both the editor and a saved document. Compare labels, wrapped text, connectors, custom icons, and accessible title/description. Record any intentional visual change in the pull request.
12. Require the CI dependency review, npm audit, license check, renderer SBOM, renderer image vulnerability scan, and renderer dependency-contract artifact. High or Critical findings block the update until remediated or explicitly dispositioned under the release security policy.
13. Record the tested commit, dependency-contract artifact, diagram-export gate, production-image rehearsal, browser results, image digest, SBOM, scan, and provenance in the release record.

Patch, minor, and major updates use the same gates. A small version number does not make rendered output compatible. Major updates additionally require a review of the supported-syntax contract and user-facing Mermaid guide before merge.

## Failure and rollback

- If preview and renderer Mermaid versions cannot be aligned, keep the current versions and open an issue describing the dependency conflict.
- If Chromium changes unexpectedly during an image build, inspect the Alpine package change before updating `CHROMIUM_SERIES`.
- If output changes, determine whether the change is an intended rendering correction. Update fixtures and documentation only after that decision is recorded.
- If a security finding cannot be resolved without breaking the diagram contract, do not merge the update. Record the finding and affected versions for release triage.
- Roll back by reverting the complete dependency update, including manifests, lockfiles, image digest or Chromium-series changes, configuration, and fixtures. Re-run the fast contract check after the revert.

Compatibility is established by the retained test and release evidence, not by dependency versions alone.

## Building the 1.0 diagram release record

Diagram evidence is split into seven value-safe JSON fragments. Each fragment names the exact candidate commit, the successful gate, an immutable run or digest identifier, and the fixed checks that gate owns. Raw browser output, document content, secrets, and scanner reports do not belong in these fragments.

The required categories are:

- `dependency_contract`: exact dependency pins, preview/renderer alignment, Chromium assertion, and controlling-file checksums.
- `authoring_and_failures`: guided/source round trips, accessibility metadata, unsupported-source preservation, and every safe failure code.
- `renderer_and_exports`: supported families, deterministic bytes, isolation, capacity, cleanup, retained integrity, STATIC atomicity, and HTML/PDF/DOCX/ZIP output.
- `browser_accessibility`: saved rendering, source editing and fallback, download, keyboard and screen-reader behavior, zoom/reflow, forced colors, print, and axe.
- `production_image`: actual export, health, runtime identity, Chromium attribution, and non-root/read-only controls.
- `upgrade_and_restore`: versioned Mermaid source upgrade plus signed publication and SVG/PNG recovery from separate database/media backup.
- `supply_chain`: dependency/license audit, renderer digest, vulnerability scan, SBOM, and provenance attestations.

Use this exact sequence for a frozen candidate:

1. Record the 40-character candidate commit. It must already be pushed; the supply-chain fragment is created only after the tested renderer image is published and attested.
2. Let **Build, test, and secure** complete for that push. Do not use fragments from a rerun of another commit.
3. Dispatch **Extended validation** against the same commit and let its supported-upgrade, versioned-diagram-source upgrade, and supported-recovery jobs complete.
4. Create an empty collection directory and download only artifacts whose names begin `tekdocs-diagram-evidence-` from those two runs. GitHub CLI example:

   ```sh
   candidate=0123456789abcdef0123456789abcdef01234567
   build_run=123456789
   extended_run=123456790
   mkdir -p artifacts/diagram-release-evidence
   gh run download "$build_run" --pattern 'tekdocs-diagram-evidence-*' --dir artifacts/diagram-release-evidence
   gh run download "$extended_run" --pattern 'tekdocs-diagram-evidence-*' --dir artifacts/diagram-release-evidence
   make assemble-diagram-release-evidence CANDIDATE_COMMIT="$candidate"
   ```

5. The assembler must report seven evidence records and the full required-check count. Missing categories, altered check inventories, duplicate categories, failed gates, future timestamps, secret-shaped content, non-digest renderer identities, or mixed candidate commits block assembly.
6. Retain `artifacts/diagram-release-evidence.json` with the 1.0 release record. Do not commit a candidate record back into the candidate it describes, and do not substitute job names or screenshots for the JSON fragments.

The assembled matrix proves the scoped automated gates ran for one candidate. It does not claim an independent security, accessibility, or compliance assessment.

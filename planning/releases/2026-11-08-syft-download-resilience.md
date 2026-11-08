# Syft download resilience after provider-fingerprint hardening

Date: November 8, 2026. Scope: restore exact-source Build evidence for
`51fb2cf9bc08a557f74fcf4a5ddc760451e993f4` without changing application,
container, scan or SBOM policy.

Acceptance criteria:

- Preserve both failed Build attempts and their exact external error.
- Keep Anchore SBOM Action and Syft pinned to reviewed immutable versions.
- Retry only the Syft tool-cache download, at most three times, before image
  SBOM generation.
- Do not weaken artifact, vulnerability, final-validation or publication gates.

## Reproduction and diagnosis

Build 42460484430 passed every source, database, browser and coverage job in
attempt 1. Its production-container job built and rehearsed the four images, then
failed before generating the first SBOM because GitHub returned HTTP 504 for
Syft v1.54.0's checksum asset. The failed-job-only attempt 2 reproduced the same
504 at the same checksum URL. `Validation passed` failed consequentially.

The pinned `anchore/sbom-action` source downloads Syft into the GitHub tool cache
when that exact version is absent; it does not retry a failed installer download.
Later SBOM steps reuse the cached command. The workflow therefore performs up to
three pinned `download-syft` sub-action attempts before the existing four SBOM
steps. A successful attempt populates the runner tool cache; three failures still
fail closed. The supply-chain contract pins the action SHA, Syft v1.54.0 and the
bounded attempt count.

This is CI transport resilience only. It changes no runtime source, schema,
image contents, scanner severity, accepted vulnerability or public workflow, so
no Wiki update is required. The next exact-source Build must pass the production
container/SBOM/vulnerability job and final `Validation passed` job. CodeQL must
also complete for the corrective commit before the stack-trace alert review is
closed out.

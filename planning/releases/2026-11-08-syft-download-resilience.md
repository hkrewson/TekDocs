# Syft download resilience after provider-fingerprint hardening

Date: November 8, 2026. Scope: restore exact-source Build evidence for
`51fb2cf9bc08a557f74fcf4a5ddc760451e993f4` without changing application,
container, scan or SBOM policy.

Acceptance criteria:

- Preserve both failed Build attempts and their exact external error.
- Keep Syft pinned to a reviewed immutable version and container-image digest.
- Generate all four SBOMs without depending on GitHub release-asset delivery.
- Do not weaken artifact, vulnerability, final-validation or publication gates.

## Reproduction and diagnosis

Build 42460484430 passed every source, database, browser and coverage job in
attempt 1. Its production-container job built and rehearsed the four images, then
failed before generating the first SBOM because GitHub returned HTTP 504 for
Syft v1.54.0's checksum asset. The failed-job-only attempt 2 reproduced the same
504 at the same checksum URL. `Validation passed` failed consequentially.

The pinned `anchore/sbom-action` source downloads Syft into the GitHub tool cache
when that exact version is absent; it does not retry a failed installer download.
Corrective Build 42469071624 proved that three bounded attempts fail closed, but
all three still depended on GitHub's release endpoint and received HTTP 503,
HTTP 000 and HTTP 503 respectively.

The workflow now runs Anchore's official Syft v1.54.0 container at immutable
multi-platform digest
`sha256:0356562f495d432056237fbea5cbc2d4839c9c75cd500784a66de2e7cc95ca7c`.
It mounts the hosted runner's Docker socket for image inspection and the
workspace for the four CycloneDX JSON outputs. This removes the unavailable
GitHub release-asset path while retaining the same Syft version, SBOM format,
artifact upload and fail-closed behavior. The supply-chain contract requires the
digest-pinned image, all four explicit Docker image scans and no remaining SBOM
Action download path.

This is CI transport resilience only. It changes no runtime source, schema,
image contents, scanner severity, accepted vulnerability or public workflow, so
no Wiki update is required. The next exact-source Build must pass the production
container/SBOM/vulnerability job and final `Validation passed` job. CodeQL must
also complete for the corrective commit before the stack-trace alert review is
closed out.

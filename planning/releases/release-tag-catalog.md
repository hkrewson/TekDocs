# Annotated release tag catalog

## Scope and acceptance

Future versioned releases must carry a short human-readable summary without
weakening immutable release identity or adding a second publication action. The
message is reviewed source data, not generated CI prose. A release must stop
before publication when its message is absent or malformed, and retrying an
already delivered annotated tag must preserve the original tag object.

This slice changes release tooling and documentation only. It does not rewrite
the historical lightweight `v0.9.19` tag, publish a new version, deploy
production, change application behavior, alter the database or modify the API.

## Contract

`planning/releases/tag-messages/vMAJOR.MINOR.PATCH.txt` contains exactly two
trimmed LF-terminated lines:

1. a factual summary of at most 120 characters;
2. `Breaking changes: none` or a concise breaking-change/operator action of at
   most 240 characters.

The ordinary version check validates the file, so a missing message fails in the
prepare job before images or attestations are published. After every release gate
passes, the finalizer verifies the four image digests and eight attestations,
creates the annotated application tag object and atomically pushes it with the
receipt tag. A retry peels an existing application tag to its commit, rejects a
different target and reuses the existing tag object.

The production updater already supports both tag shapes. It uses the peeled
application commit and companion receipt as authority; annotation text cannot
select images or bypass backup, ancestry, migration, readiness or running-image
checks.

## Evidence

`make test-release-delivery` covers message validation, missing-message failure,
first annotated publication, real Git peeling, atomic application/receipt
delivery, matching retry, conflicting targets and historical annotated-tag
discovery. The complete release-tooling suite must pass before delivery.

The live production scheduler was inspected read-only on November 5, 2026. It
runs `scripts/update-production.sh --latest` under `flock` each Sunday at 03:30
America/Chicago, retains output in `.tekdocs-production-update.log`, and was
cleanly recording v0.9.18 with verified v0.9.19 available. No deployment or
remote mutation was performed by this inspection.

The subsequent unattended-soak slice adds
`TEKDOCS_MINIMUM_RELEASE_AGE_HOURS=48` to that scheduled command. The newest
verified release remains the only candidate: a too-new release exits successfully
before backup or Docker activity and never causes fallback to an older version.
Explicit operator-selected releases remain available for urgent deployments.

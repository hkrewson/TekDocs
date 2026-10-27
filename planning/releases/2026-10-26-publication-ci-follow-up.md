# Publication lifecycle CI follow-up

October 26, 2026. Bounded #105/#106 validation repair for `cd81e5d`.
The maintainer authorized fixing both failures and rerunning validation, including
commit/push directly to main. Version remains 0.9.15; no production deployment,
new release, public workflow change or publication-history promotion is included.

## Reproduction and cause

- Build run `40323914894`, PostgreSQL shard (core-b):
  `test_canonical_host_property` failed Hypothesis's input-generation health check
  with seed `210915741988369440601619745701977068652`. The exact seed passed
  alone at ordinary CPU allocation. An unchanged copy of the committed test,
  executed after Django initialization in the existing `tekdocs` migrate service
  at 0.1 CPU, reproduced `FailedHealthCheck`: two valid inputs in 3.09 seconds,
  including a 2.994-second draw. An earlier more severe throttling probe also
  reproduced it. The default IP strategy dynamically constructs generators for
  special ranges; explicit full-space networks avoid that work. Resource
  sensitivity is verified; the cause of the hosted runner's delay is inferred,
  not established.
- Extended run `40323924826`, Supported backup and restore: executing the complete
  recovery-content fixture against a separate pytest database in the existing
  database service reproduced `PrivilegedMFARequired` at the new Git publication.
  The synthetic owner had no TOTP authenticator: the following publication
  fixture enrolled that owner too late. Production policy correctly refused.

## Changes and acceptance

The host property now draws from explicit IPv4 and IPv6 /0 networks. Both entire
address spaces remain eligible. Twelve mandatory examples cover zero/maximum,
loopback, link-local, documentation, multicast and IPv4-mapped IPv6 forms. The
round-trip assertion, example count setting and all health checks are unchanged.
The replacement passed the same seed at 0.1 CPU. Container CPU configuration is
restored by recreating only the existing idle migrate service after testing.

The content fixture enrolls its synthetic owner before publication, only during
creation. The later publication fixture reuses existing TOTP enrollment and uses
the library's activation/encryption API for new synthetic actors. Verification
modes do not enroll or replace authenticators. No MFA policy bypass is added.
A negative publication regression requires MFA failure before any publication or
artifact is created and checks that repository authority remains intact.

Local validation replays the real content fixture through creation and repeated
verification with the same digest handoff used by the shell rehearsal. The full
encrypted source/restore rehearsal creates separate Compose projects, so it
remains a hosted gate under the repository's single-local-project rule. Local
fixture execution is not evidence of archive restore or network isolation.

No migration or API change is needed. These are internal test-fixture changes;
the public Wiki behavior is unchanged and existing user-owned Wiki edits remain
untouched. No new security exception or risk acceptance is introduced.

## Validation status

Local and hosted final results are recorded in `validation-failures.json` and
this note before closeout. Failed original runs remain failures; later results
apply only to their own commit and run.

The initial local broad run reused the database after transactional focused
checks had flushed the migration-created installation singleton. That produced
seven setup-record failures (453 tests passed). This is a local harness error,
not missing schema or a product fix; the final full group uses a fresh pytest
database and the unchanged assertions. Retained development records are untouched.
The fresh test-settings run cleared those seven setup failures, but its readiness
response omitted repository status because that profile explicitly disables
repository storage (459 passed, one configuration mismatch). The final local
replay selects CI's production settings profile with a private `/tmp` repository
root, separate from retained development Git storage. This needs no product or
assertion change.

Verified locally: the full core-b selection plus the real content-fixture replay
and later-fixture MFA reuse probe passed **460 tests** with coverage, CI's
production settings, a fresh test database and the original Hypothesis seed.
The initial focused selection passed 31 checks. Backend Ruff and mypy (272 source
files), fixture syntax, version consistency and diff checks passed. Tooling ran
120 tests successfully (three optional skips). Hosted Build and Extended
validation still need to confirm the pushed source and complete encrypted restore.

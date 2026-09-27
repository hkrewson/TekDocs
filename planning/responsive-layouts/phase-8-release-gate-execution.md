# Phase 8 release-gate execution

This record tracks the final automated `make release-gate` boundary for the
pre-1.0 responsive-layout program. Version remains 0.8.46. A successful run does
not authorize deployment, publication, tagging, or a version change.

## Gate structure

The release gate covers repository checks, backend and frontend tests, bounded
capacity checks, maintained browser projects, the live browser-to-Django-to-
PostgreSQL workflow, security scans, production-image checks, clean installation,
backup/restore rehearsals, and supported-source upgrades.

Feature targets continue to include the frontend contract when run directly. In
one compound Make invocation, they now share `test-frontend`; Make executes that
prerequisite once. `check-frontend` adds API agreement, lint, type checking, the
production build, and bundle budgets without repeating the test suite. The
security target retains its separate dependency/license audit. This preserves
standalone target coverage while preventing the final gate from running the same
673-test suite almost twenty times.

The expected release plan contains three frontend-gate calls:

1. `test` once for all frontend unit/component coverage;
2. `verify` once for generated API agreement, lint, type checking, build, and
   bundle budgets;
3. `audit` once within the security boundary.

Validate this shape with `make -n release-gate`; adding another direct
`frontend-gate.sh test` or `frontend-gate.sh check` call to a feature recipe
should be replaced by the shared prerequisite.

The backend plan follows the same rule. The complete suite uses the isolated
PostgreSQL coverage boundaries from CI and divides the large core selection into
three deterministic local partitions before combining and enforcing coverage.
Separate databases preserve tests that modify cluster roles or schema without
requiring an unsafe shared-worker dependency. Hosts with at least 10 Docker CPUs
and 7 GB of Docker memory run all ten shards together; smaller hosts use two
five-shard batches. The two performance selections still run afterward because
they require opt-in markers or latency enforcement. Focused feature targets
remain independently callable during development, but the final gate does not
rerun selections already contained in the complete matrix. The assembled Compose
boundary verifies service health, email, production settings and image provenance
against the running stack; it no longer launches a second identical coverage
suite in a one-off test container. Release-script contracts check the complete
and non-overlapping shard plan plus the dry-run command shape.

## Current evidence

On 2026-09-26, commit `279c80d` repaired the constrained-device documentation
performance rehearsal for the reader-first interface and deferred the diagram
editor. Desktop and mobile throttled profiles passed the original limits. The
subsequent full release attempt passed the repository checks, the 2,410-test
backend coverage run, repeated 673-test frontend runs, public-beta capacity,
the constrained-browser performance rehearsal, API-token and webhook matrices,
and the integration backend matrix. A later redundant frontend repetition
reported one failure after 672 passes; an immediate complete rerun passed all
673 tests. Because the compound command exited nonzero, the final release gate
remains pending.

After the shared prerequisite change, `make -n release-gate` contains one test,
one verify, and one audit frontend boundary. `frontend-gate.sh verify` passes API
agreement, lint, type checking, the production build, and existing compressed
bundle budgets. The next acceptance run must execute the complete release target
from a clean commit and record its final exit status here before changing
`acceptance.json` to complete.

The clean `28a9928` release-gate attempt on 2026-09-26 reached the complete
maintained-browser matrix after passing the frontend, backend, capacity,
performance, API, integration, authorization, documentation, export, catalog,
inventory, network, and assembled-stack boundaries. The browser matrix reported
1,460 passed, 3 skipped, 15 failed, and 3 timed out. The failures exposed one
real keyboard-focus race in the editor and stale browser contracts for saved file
columns, credential drawers, recycle-bin status messages, compact custom-field
rows, and default workspace-search pagination. The gate therefore remains
pending.

The remediation slice now gives drawers an explicit initial-control focus path,
makes editor-tab focus synchronous with the rendered tab, and aligns the focused
browser fixtures with the shipped drawer and collection behavior. Its combined
browser run passes all 135 affected scenarios in Chromium, Firefox, and WebKit.
The 673-test frontend suite, the frontend verification/build boundary, 50 release-
script contract tests, and whitespace validation also pass. These focused results
do not replace the required clean full-gate rerun.

The clean `37fd5ff` release-gate attempt on 2026-09-26 passed every boundary
through the complete backend, capacity, performance, authorization, integration,
assembled-Compose, routing, network, secret-file and rendering checks. The
maintained-browser matrix then reported 1,475 passed, 3 intentionally skipped and
3 Firefox failures: two document-history widths and one 1024-pixel endpoint
drawer. Chromium and WebKit passed all applicable scenarios. All three failed
Firefox scenarios passed immediately in isolation, passed through three
six-worker repetitions with their surrounding files (60 scenarios), and the
complete Firefox project then passed 490 scenarios with its one intentional skip.
No reproducible product or test defect was found, so assertions and timeout limits
were not weakened. Because the compound release command still exited nonzero, the
release gate remains pending and `acceptance.json` remains unchanged.

A subsequent clean attempt from `be4636d` was deliberately stopped after about
40 minutes. It had passed the frontend boundaries, repository checks, the
2,410-test backend suite, capacity and constrained-browser performance, then
entered another overlapping authorization selection. Inspection confirmed that
the final target scheduled dozens of focused backend selections already covered
by the complete suite and scheduled the complete suite again inside
`test-compose`. The gate plan was consolidated before another acceptance run;
the interrupted command is not represented as release evidence.

The consolidated backend boundary passes in both bounded-batch and automatic
high-resource modes with the same 88.54% combined coverage as the prior serial
suite. On the 12-CPU, 8-GB Docker development host, the final ten-shard run used
about 2.4 GB while all workers were active and completed in about seven minutes,
down from 25 minutes 33 seconds for the serial coverage run. A contract test
proves that the three local core partitions select every applicable core test
file exactly once. This performance evidence validates the gate mechanism; the
full release target must still exit successfully before the acceptance ledger can
change.

The next clean attempt from `a6f21e3` exercised the consolidated plan. It passed
the frontend suite and verification, repository checks, the sharded backend
matrix at 88.54% coverage, capacity and constrained-browser performance, the
assembled Compose boundary, and frontend routing. The maintained-browser matrix
reported 1,477 passed, 3 intentionally skipped, and one Firefox failure in the
1440-pixel document Files/PDF scenario. That exact scenario then passed alone,
passed 12 consecutive repetitions under six-worker contention, and passed as
part of the complete 18-case document-file matrix across Chromium, Firefox, and
WebKit. The follow-up matrix completed in 16 seconds. No reproducible product or
test defect was found, so the product behavior and assertion limits remain
unchanged. The full command exited nonzero and did not reach its later security
and recovery boundaries; the release gate and acceptance ledger therefore remain
pending.

The elapsed-time investigation also showed that this final certification target
is substantially broader than an ordinary development gate. Do not repeatedly
launch it while diagnosing a focused failure. Reproduce and validate the failed
boundary first, retain the evidence here, and reserve another complete run for a
clean closure candidate with a stated expected duration.

## Remaining human boundary

The automated release gate cannot complete the technician and assistive-
technology walkthrough. Native 200% browser zoom, a real software keyboard, and
screen-reader announcements remain recorded in
`phase-8-technician-walkthrough.md`. Do not infer those human results from
Playwright coverage.

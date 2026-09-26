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

## Remaining human boundary

The automated release gate cannot complete the technician and assistive-
technology walkthrough. Native 200% browser zoom, a real software keyboard, and
screen-reader announcements remain recorded in
`phase-8-technician-walkthrough.md`. Do not infer those human results from
Playwright coverage.

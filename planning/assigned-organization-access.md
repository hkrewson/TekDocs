# Assigned organization staff access — acceptance follow-up

Status: Session 3 operator retest passed on 2026-10-18; focused verification completed below. Release candidate remains unchanged.

Scope: the Session 3 A-only staff reader must read Acceptance A documents and
assets, cannot read MSP or B through search or direct URLs, and does not affect
owner access. This is a pre-1.0 security follow-up to the 0.9.8 walkthrough.
The prior organization assignment only constrained assigned-only client
workspaces; a tenant Read-only role still permitted MSP reads.

Implementation introduces an explicit membership scope, preserving existing
access by default. Administrators must select Assigned organizations only and
add staff assignments. Invitation acceptance preserves the selected scope.
Migration 0021 adds the fields and constraints and makes invitation scope
immutable. UI controls explain the separate role and workspace choices.

Acceptance requires current-source backend policy/route tests, frontend tests,
migration checks, and a real Docker browser check of A allow / MSP and B deny.
The earlier backend results used stale images and are withdrawn as evidence
for this change. Corrected current-source results will be recorded here.

The operator should repeat Session 3 only after the local acceptance instance
has been updated. Existing manual results are retained. Hosted candidate
validation and public Wiki publication remain separate release work.

## Policy and migration contract

Staff membership workspace scope is independent of role permissions. Existing memberships
and invitations default to `tenant` (all workspaces otherwise authorized by policy).
`assigned_organizations` denies MSP workspace access and requires a direct staff
assignment for every organization, including organizations open to all authorized
staff. Custom role grants cannot bypass this boundary. Archived-organization
checks retain the same requirement. The installation owner retains access.
Only an MFA-protected actor with membership role-assignment authority can change
another staff member's scope. Client portal accounts retain their existing exact
organization boundary. Restricted staff cannot manage API tokens; existing
personal tokens remain bounded by the subject's current membership policy.

## Additional reproduced asset defect

On the same acceptance instance, A Laptop 01 still returned 404 after workspace
scope was corrected. A runtime-role query returned one base asset, but adding
`supplier__entity` returned zero rows; all other tested joins retained the asset.
The supplier organization anchor was hidden by RLS. Migration core.0195 permits
SELECT of a supplier identity referenced by an active asset in the current
workspace. It does not grant supplier workspace access or supplier writes.
A runtime-role regression covers the readable asset, denied supplier/sibling/MSP
workspaces, hidden unrelated supplier, and rejected supplier identity mutation.

## Verified locally (2026-10-17)

- Before update: real reader-a browser session returned A documents 200, MSP 200,
  B 404. This reproduced the reported MSP disclosure.
- Current-source focused backend accounts/access/invitations/portal/token and
  workspace/IDOR suite completed successfully (one skip).
- Frontend API type consistency, lint, TypeScript and production build passed.
  Six focused frontend files: 47 tests passed, including keyboard navigation and
  scope-change confirmation. Two incorrect new test selectors were corrected
  against the actual accessible labels.
- Backend ruff and mypy passed; migration drift check passed including core.0195.
- Both migration upgrade steps applied to the existing Docker acceptance database;
  all four workspace repositories reconciled unchanged. Backup retained privately.
- Reader-a restriction applied through the policy service with its existing A
  assignment. All other membership scopes were checked unchanged. Owner policy
  checks continued to allow MSP, A and B documents/assets.
- Focused runtime supplier-anchor regression passed against current source.
  The write-denial assertion expects PostgreSQL’s RLS rejection (rather than a
  zero-row update). Final ruff/mypy and migration drift checks also passed.

## Remaining release work

The broad accounts suite encountered a missing installation singleton in a
password-reset test using the reused test database. Its cause remains unverified;
that run is not a passing full-suite result. Full clean candidate validation and
hosted gates must pass before release. Earlier stale-image backend evidence is
not counted. The Wiki change is an unpublished draft. Existing operator results
and the pinned candidate manifest are preserved.

## Operator retest — passed 2026-10-18

The operator confirmed that Session 3 now passes on the updated local acceptance
instance. This closes the reported Session 3 acceptance failures. Full candidate
validation and hosted release gates remain outstanding.

Retest instructions used:

Use the existing installation at http://localhost:3298 and repeat **Session 3
only**, signing out and back in as reader-a first. Choose Acceptance A. Confirm
Laptop 01 and Runbook 01 open, MSP is absent from the workspace chooser, and direct
MSP/B document links show no content. Acceptance B should continue to exist for
the owner; it must be inaccessible to reader-a. Preserve the completed results
from the other sessions.


## Updated acceptance runtime identity

Built from the uncommitted working tree based on
`5c9a64fe08a8d22b184769b2e1ebdac4121afe8e`, not the pinned release candidate:

- Backend image: `sha256:062f19302415ef55f33edf151f13c0a7abfd11fd0b93bdce201f85da5f621457`
- Frontend image: `sha256:946426cde8e74d1accb077cf13ce9790ee3cdc7d7c9475ca0e037fd45b55d14b`
- Final real-browser checks: A document collection, Runbook 01, asset collection
  and Laptop 01 all returned 200. Matching MSP requests returned 403, B requests
  returned 404. Chooser exposed A and omitted MSP/B.

The old acceptance manifest describes the original preparation; the image IDs
above identify this local update. These results are not evidence for the pinned
release candidate or a clean committed application SHA.

Final required local gate: `make test-runtime-authorization` passed on a fresh
Docker/PostgreSQL installation: **13 passed**. This includes the retained supplier
regression and existing workspace, portal, RLS, and webhook authorization checks.
The preceding run used the earlier zero-row write assertion and failed that one
test; the corrected test expects the actual RLS exception and passed on rerun.

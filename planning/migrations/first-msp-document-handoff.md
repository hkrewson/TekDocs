# First MSP document authority handoff: readiness

Scope: issue #105, supported by #106 and proposed ADR 0115. The operator selected
an existing MSP startup guide as the first identity-preserving migration example.
Production title and identifiers are supplied at execution, not committed as
fixture data. No production copy, promotion, edit or rollback is authorized by
this readiness record.

Acceptance for this slice: inspect the existing implementation; run the existing
migration/runtime-isolation gate in disposable Docker; prepare a value-minimized,
read-only production inventory; distinguish supported behavior from remaining
handoff requirements.

## Source findings

The released source already contains `DocumentAuthority`, database guards,
`transition_document_authority`, and `prepare_rollback_markdown_projection`.
The claim that no handoff implementation exists was too broad. The roadmap and
ADR describe a broader unfinished boundary, not the absence of all transition code.

- `document_migration_inventory.py` reports exact-workspace import blockers.
- `preview_document_migration` validates a copy plan without accepting a commit.
- `import_document_migration` requires a reviewed base commit and plan hash;
  importing a copy does not promote it.
- `document_migration_coexistence.py` checks copy/read parity, authority state,
  templates, retained primary-file bytes, legacy publication history and review
  integrity before cutover readiness.
- `transition_document_authority` previews by default and requires `--apply` to
  mutate. It locks workspace/repository/document state and audits the transition.
- `prepare_rollback_markdown_projection` supports owned-fragment body edits while
  identity, root content/metadata and include structure remain unchanged. It
  appends new legacy revisions for supported changes rather than resetting Git.

The existing test `test_repository_authority_allows_git_edits_for_a_migrated_document`
covers promotion, Git edits, rejection of legacy writes, retained files/publication
evidence, body-edit rollback, and refusal of structural rollback. It also shows
that a later metadata edit can make rollback unavailable. Therefore existing
promotion is not a demonstrated guarantee of reversibility for every allowed
future edit. The broader ADR and 1.0 handoff gate remain open. Before production
promotion, either restrict edits to a proven reversible shape or implement and
validate reverse projection for those additional shapes.

Legacy publication history and template relationships remain explicit blockers.
Do not delete history or remove a blocker to make the first example eligible.
The deployment's count of legacy publications does not identify which document
owns them; the selected document must be checked independently.

## Operator read-only inventory

Run the following from the production host. It prompts for the exact existing
MSP document title and prints only match counts, disposition and blocker codes.
It does not print the document body, actor IDs, document IDs or workspace IDs.
The database transaction is explicitly read-only. A `simple_candidate` result
means inventory eligibility, not permission to promote or verified rollback.

```bash
docker exec -it tekdocs-backend-1 python manage.py shell -c '
import json
from django.db import connection, transaction
from apps.core.models import Document, InstallationState, Workspace, WorkspaceKind
from apps.core.document_migration_inventory import inventory_legacy_documents
from apps.core.rls import OrganizationRLSMode, RLSPrincipalMode, bind_local_rls_scope
from apps.core.scoping import DataScope
name = input("Exact MSP document title: ").strip()
with transaction.atomic():
    with connection.cursor() as cursor:
        cursor.execute("SET TRANSACTION READ ONLY")
    state = InstallationState.objects.get(pk=InstallationState.SINGLETON_ID)
    bind_local_rls_scope(DataScope.tenant(state.tenant), organization_mode=OrganizationRLSMode.MSP_ONLY, actor_user_id=None, principal_mode=RLSPrincipalMode.SYSTEM)
    workspace = Workspace.objects.get(tenant_id=state.tenant_id, kind=WorkspaceKind.MSP)
    matches = list(Document.objects.filter(tenant_id=state.tenant_id, organization_id=None, entity__workspace_id=workspace.id, entity__display_name=name)) if name else []
    result = {"read_only": True, "matches": len(matches)}
    if len(matches) == 1:
        inventory = inventory_legacy_documents(workspace)
        row = next(item for item in inventory["documents"] if item["document_id"] == str(matches[0].id))
        result.update(repository_blockers=inventory["repository_blockers"], disposition=row["disposition"], reasons=row["reasons"], placement_count=row["placement_count"])
    print(json.dumps(result, sort_keys=True))
'
```

If access fails, report that failure without changing database privileges. Do not
run the apply/import/transition commands as a workaround. If there are zero or
multiple matches, stop and identify the intended document locally.

## Ordered follow-up

1. Review this document's sanitized inventory result.
2. Reproduce its supported structural shape with synthetic content locally.
3. Prove copy and read parity, old-write refusal, supported Git edits, reverse
   projection and isolated recovery for that shape; close the reversibility gap.
4. Freeze and validate any required implementation before deploying it.
5. Obtain a separate production mutation approval after presenting the exact
   copy/promotion plan, backup and rollback procedure.
6. Preserve the existing content during migration. Apply the corrected startup
   guide as a subsequent reviewed Git edit so migration and editorial changes
   have separate history.

## Evidence

Initial source inspection was verified against published f52b210. The existing `make test-document-migration-inventory` test selection was run
through the repository shard runner with a temporary isolated-project adapter:
`test_document_migration_inventory.py` and `test_runtime_rls.py`, 28 passed in
122.02 seconds. The adapter used the existing Compose/migration/cleanup flow
without changing assertions or application source. Docker evidence is retained
locally in `/tmp/tekdocs-authority-readiness.log`. This validates the bounded
existing behavior, not completion of the broader handoff or recovery promise.
The operator subsequently confirmed one ordinary-document match, one placement,
`simple_candidate`, no reasons and no repository blockers. The earlier template
classification was corrected through the normal UI. Inventory eligibility is
verified by the operator's sanitized output; copy and promotion remain unapproved.

The next production preview failed because it attempted to save repository health
metadata inside the explicitly read-only transaction. No successful preview is
claimed. See [read-only preview correction](read-only-preview-correction.md).
Do not remove the read-only guard or retry the preview on unchanged v0.9.9.

## Resumed readiness — October 24, 2026

Published v0.9.12 contains the read-only preview correction. Production deployment
is unconfirmed, so no production retry, copy or promotion is claimed here.

Verified locally: the complete existing `test-document-migration-inventory`
selection (migration inventory and runtime RLS modules) passed in a fresh,
isolated Docker Compose project: 28 passed in 79.37 seconds. A temporary adapter
of the existing PostgreSQL shard runner selected these two modules and retained
normal build, migration and cleanup behavior. Log:
`/tmp/tekdocs-0912-handoff-readiness.log`. No runtime source or assertion changed.

This includes the positive copy/promotion, supported fragment-body edits,
legacy-write rejection, retained-file behavior and rollback checks, plus the
negative metadata/structural rollback refusal. The latter is still a limitation,
not proof of reversible arbitrary editing. Existing exact-workspace and read-only
preview checks also passed. Hosted 0.9.12 supported recovery remains the release
recovery evidence; this focused run is not a new production recovery exercise.

### Next bounded implementation slice

Keep first-document migration reversible by enforcing its supported edit shape
while rollback to legacy authority is promised. Acceptance criteria:

- Owned fragment Markdown body edits remain available and roll back without
  losing revisions or retained files.
- Root identity/metadata/body, fragment metadata, placement/include structure,
  and other edits outside the proven reverse projection reject before accepting
  a Git commit, with an actionable explanation.
- The restriction applies only to migrated content under the reversible handoff
  contract; native Git documents and unrelated Workspaces retain normal behavior.
- Session/API paths and low-level accepted-write paths share enforcement; allow,
  deny and cross-workspace tests exercise the actual runtime role.
- Copy, promotion, allowed edit, reverse projection and isolated recovery are
  rehearsed together before offering the production promotion plan.

This defines the next implementation, not a completed restriction. A broader
reverse-projection implementation may later expand the supported shape through
its own acceptance evidence. Do not promote production while unrestricted edits
can invalidate the promised rollback. Keep the startup-guide editorial revision
separate from migration history.

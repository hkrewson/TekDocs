# Field-key/entity migration source review

Baseline: `802d484615244f238a7d419e760a38feeacf22a9`.
Scope: uncommitted tracked diff and new files listed in the slice record,
including v9 verification/SQL guards, shared dependency freezing, migration
eligibility, Keys API/interface, manifest/index coherence and validation fixtures.
The code-review skill ran separate read-only Standards and Spec reviewers.

| Axis | Final disposition |
| --- | --- |
| Standards | Zero remaining findings; no actionable heuristic smell. |
| Spec | Zero remaining concrete findings. |

Both axes identified missing serialization between binding mutation and authority
handoff. Two database connections reproduced insert and archive succeeding across
an uncommitted promotion, in both MSP and client Workspaces (four failures).
The trigger now locks old/new owner Documents in identity order before checking
authority. API mutations lock the owner within their transaction before the
legacy-authority check. The same four tests pass after correction and assert
unchanged bindings. Both reviewers closed the finding.

The Standards reviewer also proposed a missing/null key-kind bypass in the v9 SQL
guard. Four direct SQL negatives passed before any guard change; inherited v3
validation already requires the field and string type. The reviewer retracted
the unproven finding. The negatives remain and 0207 was not changed for it.

The real browser had previously exposed stale MSP content indexing after another
client's creation. A focused read test reproduced the unavailable current reader.
Manifest-only synchronization now preserves a previously current index within
the existing coordinator, while leaving an already stale repository blocked.
Current/stale and MSP/client tests cover that boundary. A separate new browser
harness omission dismissed the existing publication confirmation; adding the
same dialog acceptance used by the old journey fixed it without loosening any
assertion or timeout. Both real journeys and server custody/rollback verification
passed again with the final binding-lock correction; the slice records
validation separately from this source review.

Review establishes source findings, not hosted validation or release acceptance.
No version, image publication, production deployment, live-data migration or Wiki
publication is included. Existing development-tool advisories have a separate
open observation, not a new accepted exception.

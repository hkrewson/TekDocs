# TDD evidence: pin document review to content

## Journey

As a documentation approver, I should only approve the exact Markdown content
that was submitted for review, so an old request cannot approve changed content.

## Evidence

| Guarantee | Test | Result |
|---|---|---|
| A review request stores the digest of its resolved Markdown, and an ordinary edit clears it. | `backend/apps/core/tests/test_document_operations.py::test_review_request_decision_and_later_edit_invalidation` | PASS |
| A pending review whose current Markdown no longer matches its retained digest cannot be approved. | `backend/apps/core/tests/test_document_operations.py::test_review_decision_refuses_a_different_pinned_content_revision` | PASS |

RED was observed before implementation: the review row had no content digest,
and the stale-content decision returned HTTP 200 instead of refusing approval.
The complete `test_document_operations.py` file passed after the change (11
tests). `makemigrations --check --dry-run` reported no model/migration drift.

Coverage was not measured. This proves legacy Markdown pinning only; Git review
still needs to pin the accepted commit and any review-relevant portable
metadata before authority handoff.

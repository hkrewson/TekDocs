"""Bounded Git-backed read acceptance, not a maximum repository capacity claim."""

import uuid

import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.core import repository_service
from apps.core.content_index import index_repository_content
from apps.core.tests.test_content_read import _content
from apps.core.tests.test_stabilization_performance import _timed_requests, assert_p95_within_budget

pytest_plugins = ("apps.core.tests.test_content_read",)
pytestmark = [pytest.mark.performance, pytest.mark.django_db(transaction=True)]


def test_git_repository_listing_composition_and_authoring_reads_stay_responsive(read_context):
    installation, organization, _asset, repository = read_context
    TOTP.activate(installation.owner, generate_totp_secret())
    document_ids = [uuid.uuid4() for _ in range(250)]
    fragment_id = uuid.uuid4()
    fragment_body = "Shared enrollment instructions.\n"
    changes = {
        "fragments/enrollment.md": _content(
            content_id=fragment_id, title="Enrollment", body=fragment_body, kind="fragment"
        ),
        **{
            f"docs/runbook-{index:03d}.md": _content(
                content_id=content_id,
                title=f"Capacity runbook {index:03d}",
                body=f"Runbook {index:03d}.\n",
                metadata=f"includes:\n  - id: {fragment_id}\n    mode: live\n    audience: shared\n",
            )
            for index, content_id in enumerate(document_ids)
        },
    }
    base = repository.accepted_commit.object_id if repository.accepted_commit else None
    paths = list(changes)
    for start in range(0, len(paths), 100):
        commit = repository_service.commit_repository_files(
            repository_id=repository.id,
            expected_base=base,
            changes={path: changes[path] for path in paths[start:start + 100]},
            message="Create Git performance reference",
        )
        base = commit.object_id
    index_repository_content(repository_id=repository.id)
    browser = Client()
    browser.force_login(installation.owner)
    scope = {"organization_entity_id": organization.entity_id}
    selected = {**scope, "content_id": document_ids[-1]}
    cases = (
        ("Git listing last page", reverse("organization-content-documents", kwargs=scope),
         {"page": 10, "page_size": 25, "kind": "document"}),
        ("Git composed read", reverse("organization-content-document-detail", kwargs=selected), {}),
        ("Git authoring source", reverse("organization-content-authoring-source", kwargs=selected), {}),
    )
    for label, url, params in cases:
        assert_p95_within_budget(label, _timed_requests(browser, url, params))
        with CaptureQueriesContext(connection) as queries:
            response = browser.get(url, params)
        assert response.status_code == 200
        print(f"performance {label}: queries={len(queries)}")
        assert len(queries) <= 64, f"{label} exceeded its 64-query ceiling"
        data = response.json()
        if label == "Git listing last page":
            assert data["count"] == 250
            assert len(data["results"]) == 25
            assert data["has_more"] is False
        elif label == "Git composed read":
            assert fragment_body.strip() in data["markdown"]
        else:
            assert data["markdown"] == "Runbook 249.\n"

from apps.core.models import DocumentTopicType
from apps.core.topic_schemas import catalog, inspect_markdown, seed_markdown


def test_topic_catalog_is_versioned_and_contains_every_supported_type():
    records = catalog()
    assert {item["type"] for item in records} == set(DocumentTopicType.values)
    assert {item["schema_version"] for item in records} == {1}


def test_seeded_procedure_is_parseable_and_only_warns_for_empty_sections():
    markdown = seed_markdown(DocumentTopicType.PROCEDURE, "Reset the edge router.")
    findings = inspect_markdown(DocumentTopicType.PROCEDURE, markdown)
    assert not [item for item in findings if item["severity"] == "blocker"]
    assert "<!-- tekdocs:section purpose -->" in markdown
    assert "Reset the edge router." in markdown


def test_missing_duplicate_and_malformed_semantics_are_blockers_without_rewriting_content():
    markdown = """<!-- tekdocs:section purpose -->
## Purpose

Keep this text.

<!-- tekdocs:section purpose -->
not a heading
"""
    findings = inspect_markdown(DocumentTopicType.PROCEDURE, markdown)
    codes = [item["code"] for item in findings if item["severity"] == "blocker"]
    assert "topic.section.duplicate" in codes
    assert "topic.section.heading_missing" in codes
    assert "topic.section.missing" in codes
    assert "Keep this text." in markdown


def test_unstructured_content_has_no_required_section_findings():
    assert inspect_markdown(DocumentTopicType.UNSTRUCTURED, "anything\n") == []

from apps.core.models import DocumentTopicType
from apps.core.topic_schemas import catalog, inspect_markdown, seed_markdown


def test_topic_catalog_is_versioned_and_contains_every_supported_type():
    records = catalog()
    assert {item["type"] for item in records} == set(DocumentTopicType.values)
    assert {item["schema_version"] for item in records} == {1}
    assert all("starter_markdown" in item for item in records)


def test_business_document_templates_have_the_expected_sections():
    by_type = {item["type"]: item for item in catalog()}
    assert [section["label"] for section in by_type[DocumentTopicType.TROUBLESHOOTING]["sections"]] == [
        "Issue",
        "Steps to reproduce",
        "Steps taken",
        "Next steps",
        "Related",
        "Resolution",
    ]
    assert [section["label"] for section in by_type[DocumentTopicType.POLICY]["sections"]] == [
        "Purpose",
        "Scope",
        "Definitions",
        "Policy statement",
        "Roles and responsibilities",
        "Compliance and consequences",
        "Related documents",
        "Revision history",
    ]
    assert [section["label"] for section in by_type[DocumentTopicType.PROCEDURE]["sections"]] == [
        "Overview",
        "Purpose",
        "Scope",
        "Responsibilities",
        "Process",
        "Related",
        "Revision history",
    ]
    assert [section["label"] for section in by_type[DocumentTopicType.GUIDE]["sections"]] == [
        "Overview",
        "Walkthrough",
        "Related",
        "Revision history",
    ]


def test_seeded_procedure_is_parseable_and_only_warns_for_empty_sections():
    markdown = seed_markdown(DocumentTopicType.PROCEDURE, "Reset the edge router.")
    findings = inspect_markdown(DocumentTopicType.PROCEDURE, markdown)
    assert not [item for item in findings if item["severity"] == "blocker"]
    assert "## Purpose" in markdown
    assert "tekdocs:section" not in markdown
    assert "Reset the edge router." in markdown


def test_seed_markdown_does_not_wrap_an_already_seeded_template_again():
    starter = seed_markdown(DocumentTopicType.POLICY)
    assert seed_markdown(DocumentTopicType.POLICY, starter) == starter


def test_missing_and_duplicate_required_headings_are_blockers_without_rewriting_content():
    markdown = """## Purpose

Keep this text.

## Purpose
"""
    findings = inspect_markdown(DocumentTopicType.PROCEDURE, markdown)
    codes = [item["code"] for item in findings if item["severity"] == "blocker"]
    assert "topic.section.duplicate" in codes
    assert "topic.section.missing" in codes
    assert "Keep this text." in markdown


def test_legacy_section_comments_are_removed_when_markdown_is_seeded_again():
    legacy = "<!-- tekdocs:section purpose -->\n## Purpose\n\nText\n"
    converted = seed_markdown(DocumentTopicType.POLICY, legacy)
    assert "tekdocs:section" not in converted
    assert "## Purpose" in converted
    assert "Text" in converted


def test_unstructured_content_has_no_required_section_findings():
    assert inspect_markdown(DocumentTopicType.UNSTRUCTURED, "anything\n") == []

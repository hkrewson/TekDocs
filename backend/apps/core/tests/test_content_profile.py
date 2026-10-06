from __future__ import annotations

import uuid

import pytest

from apps.core.content_profile import ContentProfileError, parse_content


def _source(*, content_id: uuid.UUID, body: str, extra: str = "") -> bytes:
    return (
        f"---\nschema: tekdocs.content/v1\nid: {content_id}\nkind: document\ntitle: Recovery guide\n{extra}---\n{body}"
    ).encode()


def test_version_one_profile_parses_portable_metadata_and_bounded_wikilinks():
    target = uuid.uuid4()
    parsed = parse_content(
        _source(
            content_id=uuid.uuid4(),
            extra=("properties:\n  audience: technicians\n  reviewed: true\ntaxonomies:\n  technology:\n    - apple\n"),
            body=f"Use [[{target}#setup|the setup fragment]].\n\n`[[{uuid.uuid4()}]]`\n",
        )
    )

    assert parsed.properties == {"audience": "technicians", "reviewed": True}
    assert parsed.taxonomies == {"technology": ["apple"]}
    assert [(link.target_content_id, link.fragment, link.label) for link in parsed.links] == [
        (target, "setup", "the setup fragment")
    ]
    assert len(parsed.content_digest) == 64


@pytest.mark.parametrize(
    ("source", "code"),
    (
        (b"# no frontmatter\n", "frontmatter.missing"),
        (
            b"---\nschema: tekdocs.content/v1\nid: nope\nkind: document\ntitle: Invalid\n---\n",
            "frontmatter.id",
        ),
        (
            b"---\nschema: tekdocs.content/v1\nid: 00000000-0000-4000-8000-000000000001\n"
            b"kind: document\ntitle: Invalid\nsecret: no\n---\n",
            "frontmatter.field",
        ),
    ),
)
def test_invalid_profile_fails_with_stable_diagnostic(source: bytes, code: str):
    with pytest.raises(ContentProfileError) as captured:
        parse_content(source)
    assert captured.value.code == code


def test_malformed_wikilinks_fail_while_code_examples_remain_literal():
    with pytest.raises(ContentProfileError) as captured:
        parse_content(_source(content_id=uuid.uuid4(), body="Broken [[not-an-id]].\n"))
    assert captured.value.code == "wikilink.syntax"

    parsed = parse_content(_source(content_id=uuid.uuid4(), body="```text\n[[not-an-id]]\n```\n"))
    assert parsed.links == ()


@pytest.mark.parametrize("alias", ("docs/../other.md", "docs/.GIT/config.md", "-unsafe.md", "docs//other.md"))
def test_aliases_obey_repository_path_safety(alias: str):
    with pytest.raises(ContentProfileError) as captured:
        parse_content(_source(content_id=uuid.uuid4(), extra=f"aliases:\n  - {alias}\n", body="Guide.\n"))
    assert captured.value.code == "alias.shape"


def test_profile_parses_ordered_live_pinned_copy_and_template_source_metadata():
    live_id = uuid.uuid4()
    pinned_id = uuid.uuid4()
    source_id = uuid.uuid4()
    pinned_commit = "a" * 40
    parsed = parse_content(
        _source(
            content_id=uuid.uuid4(),
            extra=(
                "includes:\n"
                f"  - id: {live_id}\n"
                "    mode: live\n"
                "    audience: shared\n"
                f"  - id: {pinned_id}\n"
                "    mode: pinned\n"
                "    audience: msp_internal\n"
                f"    commit: {pinned_commit}\n"
                "template_sources:\n"
                f"  - id: {source_id}\n"
                f"    commit: {pinned_commit}\n"
            ),
            body="Template body.\n",
        )
    )

    assert [(item.target_content_id, item.mode, item.audience) for item in parsed.includes] == [
        (live_id, "live", "shared"),
        (pinned_id, "pinned", "msp_internal"),
    ]
    assert parsed.includes[1].pinned_object_id == pinned_commit
    assert [(item.content_id, item.object_id) for item in parsed.template_sources] == [(source_id, pinned_commit)]


@pytest.mark.parametrize(
    ("extra", "code"),
    (
        (
            f"includes:\n  - id: {uuid.uuid4()}\n    mode: live\n    audience: shared\n    commit: {'a' * 40}\n",
            "include.shape",
        ),
        (
            f"includes:\n  - id: {uuid.uuid4()}\n    mode: pinned\n    audience: everyone\n    commit: {'a' * 40}\n",
            "include.audience",
        ),
        (
            f"derived_from:\n  id: {uuid.uuid4()}\n  commit: {'A' * 40}\n",
            "derived_from.commit",
        ),
    ),
)
def test_profile_rejects_ambiguous_or_unbounded_composition_metadata(extra: str, code: str):
    with pytest.raises(ContentProfileError) as captured:
        parse_content(_source(content_id=uuid.uuid4(), body="Body.\n", extra=extra))
    assert captured.value.code == code


def test_profile_parses_typed_and_narrative_entity_links_without_code_examples():
    asset_id = uuid.uuid4()
    model_id = uuid.uuid4()
    ignored = uuid.uuid4()
    parsed = parse_content(
        _source(
            content_id=uuid.uuid4(),
            extra=f"entity_links:\n  - id: {asset_id}\n    relationship: setup\n",
            body=(f"See [model setup](tekdocs://entity/{model_id}).\n\n`[example](tekdocs://entity/{ignored})`\n"),
        )
    )
    assert [(link.target_entity_id, link.relationship, link.origin) for link in parsed.entity_links] == [
        (asset_id, "setup", "typed"),
        (model_id, "mention", "narrative"),
    ]


@pytest.mark.parametrize(
    ("extra", "body", "code"),
    (
        (f"entity_links:\n  - id: {uuid.uuid4()}\n    relationship: unknown\n", "Body.\n", "entity_link.relationship"),
        ("entity_links:\n  - id: nope\n    relationship: setup\n", "Body.\n", "entity_link.target"),
        ("", "[bad](tekdocs://entity/not-a-uuid)\n", "entity_link.uri"),
    ),
)
def test_profile_rejects_invalid_entity_link_metadata(extra: str, body: str, code: str):
    with pytest.raises(ContentProfileError) as captured:
        parse_content(_source(content_id=uuid.uuid4(), body=body, extra=extra))
    assert captured.value.code == code

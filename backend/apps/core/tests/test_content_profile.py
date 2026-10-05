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

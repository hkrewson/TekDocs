"""Foreign template fragments require an explicit authorized library resolver."""

import uuid

import pytest
import yaml

from apps.core.content_composition import ContentCompositionError, ContentCompositionResolver
from apps.core.content_profile import parse_content


def content(identity, kind, body, **metadata):
    frontmatter = dict(schema="tekdocs.content/v1", id=str(identity), kind=kind, title="Library fixture", **metadata)
    return parse_content(("---\n" + yaml.safe_dump(frontmatter) + "---\n" + body).encode())


@pytest.mark.parametrize("mode", ["live", "pinned"])
def test_library_fragment_resolution_records_exact_workspace_and_selected_commit(mode):
    root_id, source_id, workspace_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    selected, client_head = "a" * 40, "b" * 40
    include = dict(
        id=str(source_id),
        mode=mode,
        audience="shared",
        library_workspace=str(workspace_id),
        library_revision=str(uuid.uuid4()),
    )
    if mode == "pinned":
        include["commit"] = selected
    root = content(root_id, "document", "Client introduction.\n", includes=[include])
    source = content(source_id, "fragment", "Selected MSP instructions.\n")
    calls = []

    def load_library(document_id, reference):
        calls.append((document_id, reference.library_workspace_id, reference.mode, reference.pinned_object_id))
        return selected, source

    resolver = ContentCompositionResolver(
        accepted_object_id=client_head,
        accepted={root_id: root},
        loader=lambda _: {},
        library_loader=load_library,
    )
    result = resolver.resolve(content_id=root_id, audience=None)
    assert result.markdown == "Client introduction.\n\nSelected MSP instructions.\n"
    assert result.manifest[0]["workspace"] == str(workspace_id)
    assert result.manifest[0]["commit"] == selected
    assert result.manifest[0]["mode"] == mode
    assert calls == [(root_id, workspace_id, mode, selected if mode == "pinned" else "")]


def test_library_reference_never_resolves_to_same_id_in_client_repository():
    root_id, source_id, workspace_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    root = content(
        root_id,
        "document",
        "",
        includes=[
            dict(
                id=str(source_id),
                mode="live",
                audience="shared",
                library_workspace=str(workspace_id),
                library_revision=str(uuid.uuid4()),
            )
        ],
    )
    local = content(source_id, "fragment", "Unrelated same-ID client content.\n")
    resolver = ContentCompositionResolver(
        accepted_object_id="a" * 40,
        accepted={root_id: root, source_id: local},
        loader=lambda _: {},
    )
    with pytest.raises(ContentCompositionError, match="authorized template library"):
        resolver.resolve(content_id=root_id, audience=None)


def test_library_pin_cannot_be_retargeted_by_loader():
    root_id, source_id, workspace_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    root = content(
        root_id,
        "document",
        "",
        includes=[
            dict(
                id=str(source_id),
                mode="pinned",
                audience="shared",
                commit="a" * 40,
                library_workspace=str(workspace_id),
                library_revision=str(uuid.uuid4()),
            )
        ],
    )
    resolver = ContentCompositionResolver(
        accepted_object_id="b" * 40,
        accepted={root_id: root},
        loader=lambda _: {},
        library_loader=lambda *_: ("c" * 40, content(source_id, "fragment", "New source.\n")),
    )
    with pytest.raises(ContentCompositionError, match="selected commit"):
        resolver.resolve(content_id=root_id, audience=None)


@pytest.mark.parametrize(
    "body,allowed",
    [
        ("[File](tekdocs&#58;//attachment/" + str(uuid.uuid4()) + ")", False),
        ("`tekdocs://attachment/" + str(uuid.uuid4()) + "`", True),
    ],
)
def test_library_file_boundary_uses_rendered_link_semantics(body, allowed):
    root_id, source_id, workspace_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    root = content(
        root_id,
        "document",
        "",
        includes=[
            dict(
                id=str(source_id),
                mode="live",
                audience="shared",
                library_workspace=str(workspace_id),
                library_revision=str(uuid.uuid4()),
            )
        ],
    )
    resolver = ContentCompositionResolver(
        accepted_object_id="b" * 40,
        accepted={root_id: root},
        loader=lambda _: {},
        library_loader=lambda *_: ("a" * 40, content(source_id, "fragment", body)),
    )
    if allowed:
        assert body in resolver.resolve(content_id=root_id, audience=None).markdown
    else:
        with pytest.raises(ContentCompositionError, match="independent text fragments"):
            resolver.resolve(content_id=root_id, audience=None)


def test_foreign_reference_names_its_immutable_template_version():
    from apps.core.content_profile import ContentProfileError

    with pytest.raises(ContentProfileError, match="template revision"):
        content(
            uuid.uuid4(),
            "document",
            "",
            includes=[
                dict(
                    id=str(uuid.uuid4()),
                    mode="pinned",
                    audience="shared",
                    commit="a" * 40,
                    library_workspace=str(uuid.uuid4()),
                )
            ],
        )


@pytest.mark.parametrize(
    "body",
    [
        "[Field](tekdocs://key/subject.name)",
        "[Field](tekdocs&#58;//key/subject.name)",
    ],
)
def test_foreign_template_text_cannot_adopt_client_field_key_bindings(body):
    root_id, source_id, workspace_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    root = content(
        root_id,
        "document",
        "",
        includes=[
            dict(
                id=str(source_id),
                mode="live",
                audience="shared",
                library_workspace=str(workspace_id),
                library_revision=str(uuid.uuid4()),
            )
        ],
    )
    resolver = ContentCompositionResolver(
        accepted_object_id="b" * 40,
        accepted={root_id: root},
        loader=lambda _: {},
        library_loader=lambda *_: ("a" * 40, content(source_id, "fragment", body)),
    )
    with pytest.raises(ContentCompositionError, match="independent text fragments"):
        resolver.resolve(content_id=root_id, audience=None)


def test_enrolled_parent_section_resolves_only_its_body_and_preserves_the_client_child_copy():
    root_id, parent_id, original_child_id, client_child_id, workspace_id = [uuid.uuid4() for _ in range(5)]
    parent = content(parent_id, "fragment", "Parent instructions.\n", includes=[dict(
        id=str(original_child_id), mode="live", audience="shared",
    )])
    client_child = content(client_child_id, "fragment", "Client-custom child instructions.\n")
    root = content(root_id, "document", "", includes=[
        dict(id=str(parent_id), mode="live", audience="shared", library_workspace=str(workspace_id),
             library_revision=str(uuid.uuid4())),
        dict(id=str(client_child_id), mode="live", audience="shared"),
    ])
    resolver = ContentCompositionResolver(
        accepted_object_id="b" * 40, accepted={root_id: root, client_child_id: client_child}, loader=lambda _: {},
        library_loader=lambda *_: ("a" * 40, parent),
    )
    resolved = resolver.resolve(content_id=root_id, audience=None)
    assert resolved.markdown == "Parent instructions.\n\nClient-custom child instructions.\n"
    assert [item["id"] for item in resolved.manifest] == [str(parent_id), str(client_child_id)]
    assert resolved.manifest[0]["digest"] == parent.content_digest


def test_library_and_client_identifiers_do_not_share_a_cycle_namespace():
    identity, workspace_id = uuid.uuid4(), uuid.uuid4()
    root = content(identity, "document", "Client body.\n", includes=[dict(
        id=str(identity), mode="live", audience="shared", library_workspace=str(workspace_id),
        library_revision=str(uuid.uuid4()),
    )])
    source = content(identity, "fragment", "Approved source body.\n")
    resolver = ContentCompositionResolver(
        accepted_object_id="a" * 40, accepted={identity: root}, loader=lambda _: {},
        library_loader=lambda *_: ("a" * 40, source),
    )
    assert resolver.resolve(content_id=identity, audience=None).markdown == "Client body.\n\nApproved source body.\n"

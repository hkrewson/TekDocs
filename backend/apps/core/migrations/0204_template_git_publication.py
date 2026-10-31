"""Admit scoped enrolled-library proof without changing signed v1-v7 contracts."""

from importlib import import_module

from django.db import migrations

V7 = import_module("apps.core.migrations.0198_shared_git_publication").V7
# Reuse the complete ordinary shared-snapshot guard, with an explicit separate
# version branch. Foreign custody has its own enrollment/index checks below.
_START = V7.index("  IF NEW.manifest->>'format' = 'tekdocs-static-publication/v7' THEN")
_BRANCH = V7[_START:V7.rindex("  RETURN NEW;")]

LIBRARY_EDGE = r"""
EXISTS (
  SELECT 1 FROM core_documenttemplateenrollment enrollment
  JOIN core_document source_template ON source_template.id=enrollment.source_template_id
  JOIN core_entity source_entity ON source_entity.id=source_template.entity_id
  JOIN core_documenttemplaterevision version ON version.id=enrollment.applied_revision_id
  JOIN core_workspacerepository library ON library.workspace_id=source_entity.workspace_id
  JOIN core_repositorycommit selected ON selected.repository_id=library.id
  JOIN core_repositorycommit accepted ON accepted.id=library.accepted_commit_id
  JOIN core_documentauthority source_authority
    ON source_authority.workspace_id=library.workspace_id AND source_authority.content_id=source_template.id
  LEFT JOIN core_documentplacement parent
    ON parent.id=p.parent_id AND parent.document_id=d.id AND parent.tenant_id=NEW.tenant_id
  LEFT JOIN core_block owned_parent ON owned_parent.id=parent.block_id AND owned_parent.tenant_id=NEW.tenant_id
  JOIN core_contentnode parent_node ON parent_node.repository_id=r.id
    AND parent_node.tenant_id=NEW.tenant_id AND parent_node.indexed_commit_id=r.accepted_commit_id
    AND ((p.parent_id IS NULL AND parent_node.content_id=d.id)
      OR (p.parent_id IS NOT NULL AND owned_parent.source_document_id=d.id
        AND parent_node.content_id=parent.block_id))
  JOIN core_contentinclude edge ON edge.source_id=parent_node.id AND edge.target_content_id=b.id
  CROSS JOIN LATERAL jsonb_array_elements(NEW.manifest->'git_source'->'sources') proof
  CROSS JOIN LATERAL jsonb_array_elements(enrollment.placement_map) mapped
  WHERE enrollment.destination_document_id=d.id AND enrollment.tenant_id=NEW.tenant_id
    AND enrollment.organization_id IS NOT DISTINCT FROM NEW.organization_id AND enrollment.archived_at IS NULL
    AND source_template.id=b.source_document_id AND source_template.tenant_id=NEW.tenant_id
    AND source_template.organization_id IS NULL AND source_template.is_template
    AND source_template.library_visible AND source_template.archived_at IS NULL AND b.library_visible
    AND source_authority.authority='repository' AND library.tenant_id=NEW.tenant_id
    AND library.lifecycle_state='active' AND library.workspace_id<>r.workspace_id
    AND edge.library_workspace_id=library.workspace_id AND edge.library_revision_id=version.id
    AND edge.resolution_mode=p.resolution_mode AND edge.audience_profile=p.audience_profile
    AND edge.ordinal=(SELECT count(*) FROM core_documentplacement sibling
      WHERE sibling.document_id=d.id AND sibling.parent_id IS NOT DISTINCT FROM p.parent_id
        AND (sibling.position, sibling.id)<(p.position, p.id))
    AND (proof->'ordinal_path'->>-1)::integer=edge.ordinal
    AND proof->>'id'=b.id::text AND proof->>'mode'=p.resolution_mode
    AND proof->>'audience'=p.audience_profile
    AND proof->>'library_workspace'=library.workspace_id::text
    AND proof->>'repository_id'=library.id::text AND proof->>'template_revision'=version.id::text
    AND proof->>'template_checksum'=version.checksum AND proof->'body_only'='true'::jsonb
    AND proof->>'commit'=edge.resolved_object_id AND proof->>'content_digest'=edge.resolved_content_digest
    AND proof->>'commit'=selected.object_id AND proof->>'object_format'=selected.object_format
    AND proof->>'accepted_commit'=accepted.object_id
    AND (p.resolution_mode<>'live' OR selected.id=accepted.id)
    AND mapped->>'source_block_id'=b.entity_id::text
    AND mapped->>'destination_placement_id'=p.id::text AND mapped->>'mode'=p.resolution_mode
    AND (p.resolution_mode<>'pinned' OR p.pinned_revision_id::text=mapped->>'applied_revision_id')
    AND (proof->>'path'='fragments/' || b.id::text || '.md' OR (
      p.resolution_mode='pinned' AND proof->>'path'=
        'template-snapshots/' || version.id::text || '/fragments/' || b.id::text || '.content'
    ))
)
"""
SOURCE_CERTIFICATE = r"""
EXISTS (
  SELECT 1 FROM core_document template
  JOIN core_documenttemplaterevision definition ON definition.template_id=template.id
  JOIN core_entity template_entity ON template_entity.id=template.entity_id
  WHERE template.id=NEW.document_id AND template.tenant_id=NEW.tenant_id
    AND template.is_template AND template.organization_id IS NULL AND definition.tenant_id=NEW.tenant_id
    AND definition.manifest->>'template_document_id'=template.entity_id::text
    AND definition.manifest->>'title'=template_entity.display_name
    AND definition.manifest->>'topic_type'=template.topic_type
    AND definition.manifest->>'topic_schema_version'=template.topic_schema_version::text
    AND NEW.manifest->'template_source'->>'content_id'=template.id::text
    AND NEW.manifest->'template_source'->>'revision'=definition.id::text
    AND NEW.manifest->'template_source'->>'checksum'=definition.checksum
    AND definition.manifest ?& ARRAY[
      'template_document_id', 'title', 'topic_type', 'topic_schema_version', 'taxonomies', 'blocks'
    ]
    AND definition.manifest - ARRAY[
      'template_document_id', 'title', 'topic_type', 'topic_schema_version', 'taxonomies', 'blocks'
    ] = '{}'::jsonb
    AND jsonb_typeof(definition.manifest->'blocks')='array'
    AND jsonb_array_length(definition.manifest->'blocks')=(
      SELECT count(*) FROM core_documentplacement p WHERE p.document_id=template.id
    )
    AND (
      SELECT jsonb_agg(item - 'attachment_ids' ORDER BY ordinal)
      FROM jsonb_array_elements(definition.manifest->'blocks') WITH ORDINALITY declared(item, ordinal)
    ) IS NOT DISTINCT FROM (
      WITH RECURSIVE ordered AS (
        SELECT p.*, row_number() OVER (PARTITION BY p.parent_id ORDER BY p.position, p.id)-1 AS ordinal
        FROM core_documentplacement p WHERE p.document_id=template.id
      ), tree AS (
        SELECT p.id, p.block_id, p.resolution_mode, p.pinned_revision_id, p.audience_profile,
          0 AS depth, ARRAY[p.ordinal] AS path
        FROM ordered p WHERE p.parent_id IS NULL
        UNION ALL
        SELECT p.id, p.block_id, p.resolution_mode, p.pinned_revision_id, p.audience_profile,
          parent.depth+1, parent.path || p.ordinal
        FROM ordered p JOIN tree parent ON parent.id=p.parent_id WHERE parent.depth<31
      )
      SELECT jsonb_agg(jsonb_build_object(
        'source_block_id', b.entity_id::text, 'source_revision_id', revision.id::text,
        'checksum', revision.checksum, 'kind', b.kind, 'name', block_entity.display_name,
        'depth', tree.depth, 'audience_profile', tree.audience_profile
      ) ORDER BY tree.path)
      FROM tree JOIN core_block b ON b.id=tree.block_id
      JOIN core_blockrevision revision ON revision.id=CASE WHEN tree.resolution_mode='live'
        THEN b.current_revision_id ELSE tree.pinned_revision_id END
      JOIN core_entity block_entity ON block_entity.id=b.entity_id
      WHERE b.source_document_id=template.id AND b.tenant_id=NEW.tenant_id
        AND revision.tenant_id=NEW.tenant_id
    )
    AND jsonb_typeof(definition.manifest->'taxonomies')='array'
    AND NOT EXISTS (
      SELECT 1 FROM core_documenttaxonomyterm assignment
      WHERE assignment.document_id=template.id AND assignment.local_term_id IS NOT NULL
    )
    AND (
      SELECT COALESCE(jsonb_agg(
        (taxonomy - 'terms') || jsonb_build_object('terms', (
          SELECT COALESCE(jsonb_agg(term ORDER BY term->>'key', term->>'label', term::text), '[]'::jsonb)
          FROM jsonb_array_elements(taxonomy->'terms') term
        )) ORDER BY taxonomy->>'taxonomy_key', taxonomy->>'taxonomy_version'
      ), '[]'::jsonb)
      FROM jsonb_array_elements(definition.manifest->'taxonomies') taxonomy
    ) IS NOT DISTINCT FROM (
      SELECT COALESCE(jsonb_agg(jsonb_build_object(
        'taxonomy_key', taxonomy.key, 'taxonomy_version', version.version,
        'label', version.label, 'terms', selections.terms
      ) ORDER BY taxonomy.key, version.version::text), '[]'::jsonb)
      FROM (
        SELECT assignment.taxonomy_id, term.version_id,
          jsonb_agg(jsonb_build_object('key', term.stable_key, 'label', term.label)
            ORDER BY term.stable_key, term.label) AS terms
        FROM core_documenttaxonomyterm assignment JOIN core_taxonomyterm term ON term.id=assignment.term_id
        WHERE assignment.document_id=template.id AND assignment.tenant_id=NEW.tenant_id
          AND term.tenant_id=NEW.tenant_id
        GROUP BY assignment.taxonomy_id, term.version_id
      ) selections JOIN core_taxonomy taxonomy ON taxonomy.id=selections.taxonomy_id
      JOIN core_taxonomyversion version ON version.id=selections.version_id
    )
    AND NOT EXISTS (
      SELECT 1 FROM jsonb_array_elements(definition.manifest->'blocks') item
      WHERE jsonb_typeof(item->'attachment_ids') IS DISTINCT FROM 'array' OR NOT EXISTS (
        SELECT 1 FROM core_documentplacement p JOIN core_block b ON b.id=p.block_id
        JOIN core_blockrevision version ON version.id=COALESCE(p.pinned_revision_id, b.current_revision_id)
        JOIN core_entity block_entity ON block_entity.id=b.entity_id
        WHERE p.document_id=template.id AND b.source_document_id=template.id
          AND version.tenant_id=NEW.tenant_id AND b.tenant_id=NEW.tenant_id
          AND item->>'kind'=b.kind AND item->>'name'=block_entity.display_name
          AND b.entity_id::text=item->>'source_block_id' AND version.id::text=item->>'source_revision_id'
          AND version.checksum=item->>'checksum'
      )
    )
)
"""

V8_BRANCH = (
    _BRANCH.replace("'tekdocs-static-publication/v7'", "'tekdocs-static-publication/v8'", 1)
    .replace("AND NOT d.is_template", "AND (NOT d.is_template OR " + SOURCE_CERTIFICATE + ")")
    .replace("'tekdocs.git-dependencies/v1'", "'tekdocs.git-dependencies/v2'")
    .replace("count(DISTINCT s->>'id')", "count(DISTINCT (COALESCE(s->>'library_workspace', "
             "NEW.manifest->'git_source'->>'workspace_id'), s->>'id'))")
    .replace("'mode', s->'mode', 'audience', s->'audience', 'ordinal_path', s->'ordinal_path'\n            )",
             """'mode', s->'mode', 'audience', s->'audience', 'ordinal_path', s->'ordinal_path'
            ) || CASE WHEN s ? 'library_workspace' THEN jsonb_build_object(
                'workspace', s->'library_workspace', 'template_revision', s->'template_revision'
            ) ELSE '{}'::jsonb END""")
    .replace("LEFT JOIN core_documentauthority ba ON ba.workspace_id=r.workspace_id AND ba.content_id=b.id",
             "LEFT JOIN core_documentauthority ba ON ba.workspace_id=oe.workspace_id AND ba.content_id=b.id")
    .replace("p.audience_profile <> 'shared' OR oe.workspace_id <> r.workspace_id\n"
             "              OR b.tenant_id <> NEW.tenant_id\n"
             "              OR b.organization_id IS DISTINCT FROM NEW.organization_id\n"
             "              OR (p.resolution_mode='live' AND ba.authority IS DISTINCT FROM 'repository')",
             "p.audience_profile <> 'shared' OR b.tenant_id <> NEW.tenant_id\n"
             "              OR NOT ((oe.workspace_id=r.workspace_id "
             "AND b.organization_id IS NOT DISTINCT FROM NEW.organization_id "
             "AND (p.resolution_mode<>'live' OR ba.authority IS NOT DISTINCT FROM 'repository')) OR " + LIBRARY_EDGE + ")")
    .replace("    THEN RAISE EXCEPTION 'shared Git publication source is invalid';", """      OR NOT ((NEW.manifest ? 'template_source' AND """ + SOURCE_CERTIFICATE + """
            AND NOT EXISTS (
              SELECT 1 FROM jsonb_array_elements(NEW.manifest->'git_source'->'sources') s
              WHERE s ? 'library_workspace'
            )) OR (NOT (NEW.manifest ? 'template_source') AND EXISTS (
              SELECT 1 FROM jsonb_array_elements(NEW.manifest->'git_source'->'sources') s
              WHERE s ? 'library_workspace'
            )))
    THEN RAISE EXCEPTION 'template Git publication source is invalid';""")
)
V8 = (
    V7.replace("'tekdocs-static-publication/v7')",
               "'tekdocs-static-publication/v7', 'tekdocs-static-publication/v8')", 1)
    .replace("(NEW.manifest->>'format' = 'tekdocs-static-publication/v7' ",
             "(NEW.manifest->>'format' IN ('tekdocs-static-publication/v7', 'tekdocs-static-publication/v8') ")
    .replace("  RETURN NEW;", V8_BRANCH + "  RETURN NEW;")
)


class Migration(migrations.Migration):
    dependencies = [("core", "0203_template_live_rollback_closure")]
    operations = [migrations.RunSQL(V8, V7)]

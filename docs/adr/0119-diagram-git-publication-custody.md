# ADR 0119: Diagram-bearing Git publication custody

**Date**: 2026-10-31

**Status**: accepted for the bounded development slice; local validation passed, exact-source hosted validation pending

**Deciders**: TekDocs maintainer

## Context

The completed content-key slice still blocks Mermaid diagrams from internal Git
publication and refuses older signed SVG/PNG history during migration. Authored
Mermaid lives in append-only block revisions before migration and accepted Git
objects afterward. Rendering must never replace canonical source or rewrite an
older signed artifact. Existing renderer, sanitizer, artifact, file and publication
control contracts already provide the required primitives.

## Decision

Admit verified retained diagram artifacts into the existing migration history
assessment. Read their actual bytes, validate their source/artifact associations,
and preserve stable identities, signatures, control events, all source revisions,
managed-file versions and PDFs. Invalid retained custody blocks migration and
rollback. Migration preserves source without claiming a new render.

New diagram-bearing internal Git publications use STATIC v11. The signed
`content_format` names the existing v5-v10 content certificate, including shared,
pinned, template and frozen-key proof. The diagram layer retains ordered source
metadata/checksums, actual renderer version, exact SVG/PNG artifact identities,
names, media types, bounded sizes and checksums. Required rendering and sanitization
use the maintained isolated renderer before insertion; failure leaves no new
publication or retained file. PDF, HTML and retained graphics use the same render.

Offline structural verification first checks the diagram layer against signed
canonical Markdown and descriptors, then checks a local view of the underlying
content certificate with diagrams removed. Signatures always cover the complete
original manifest. SQL similarly validates the diagram layer and a local content
view using the previous guard; it never changes NEW.manifest. Artifact insertion
continues to check original descriptors and scope. Previous signed v1-v10 formats
and their validation branches retain their semantics. Normal schema reversal
restores the previous guard without rewriting retained publications.

The frontend artifact contract includes SVG/PNG, and publication Downloads exposes
these files through the existing authorized endpoint and translated file layout.
No new authentication, renderer dependency, diagram family or external renderer
is introduced. Current source views retain their accessible source fallback.

## Consequences

Later Git edits affect future snapshots, while retained publications and downloads
remain independent of current source and renderer availability. Rollback appends
current Git text to its original block without discarding any prior revision.
Re-promotion remains possible only with complete verified custody.

Hosted fresh/0.8.46 upgrade seeds real legacy diagram publications, using the
maintained isolated renderer in the same rehearsal project; the old publisher
still creates and signs those records. Recovery compares source revisions,
signatures, every retained graphic/file/PDF byte, control events and Git objects
across an independent encrypted, network-isolated restore. Local tests reuse the
single existing project and test database; independent stacks remain hosted-only.

This is bounded development on 0.9.16. General cross-Workspace reuse, client portal
delivery and aggregate 1.0 acceptance remain separate. No release, production
migration or risk renewal is implied. Complete source review and exact-source
validation are required before completion.

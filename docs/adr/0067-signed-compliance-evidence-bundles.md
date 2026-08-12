# ADR 0067: Signed compliance evidence bundles

Date: 2026-08-12

Status: Accepted for `0.7.5`

Compliance evidence bundles freeze the authorized Workspace's exact assignment revisions, evidence links and collection windows, and risk outcomes in canonical sorted JSON. TekDocs hashes the bytes with SHA-256 and signs the digest with the existing deployment Ed25519 publication key. The database retains public verification material, never the private key. Bundle rows and their Entity ownership are immutable and forced-RLS scoped. A bundle proves integrity of a TekDocs snapshot; it does not establish external certification.

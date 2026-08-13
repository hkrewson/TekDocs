# ADR 0075: Monitoring stabilization

Date: 2026-08-12

Status: Accepted for `0.7.13`

Domain and certificate monitoring remain exact-Workspace documentation evidence, not authoritative DNS, registrar, or certificate-management systems. Collection normalizes domain names through IDNA at the boundary, treats malformed labels and ambiguous wildcards as errors, and allows a certificate wildcard to match exactly one label. DNS-over-HTTPS responses must be successful typed envelopes; unrelated answer types are ignored. CAA records and recursive-resolver DNSSEC validation are retained as explicit bounded summaries rather than inferred from a general DNS digest.

Successful terminal runs receive SHA-256 digests over a versioned canonical projection of every retained evidence field. These digests provide deterministic integrity evidence, not authenticity of the remote source. PostgreSQL requires valid digests on successful runs and prevents terminal updates and deletion; forced RLS retains exact Workspace isolation. The migration temporarily disables only the two terminal-run guards inside its atomic transaction to enrich existing successful rows, then restores and hardens them.

Certificate leaf and chain bytes, chain count, SAN count, and SAN value length are bounded before retained reduction. APIs return only the latest bounded history window. The stabilization gate combines hostile protocol fixtures, large-history query ceilings, accessibility assertions, the full route/IDOR and runtime-RLS matrices, an exact `0.7.12` upgrade with pre-existing successful evidence, and an independent database/media restore.

# ADR 0073: Safe RDAP and DNS monitoring

Date: 2026-08-12

Status: Accepted for `0.7.11`

Domain monitoring is asynchronous exact-Workspace work. Manual requests and the hourly scheduler create bounded jobs; workers collect RDAP and apex DNS evidence through the shared approved public-HTTPS egress service. DNS uses an operator-configurable DNS-over-HTTPS resolver because arbitrary UDP/TCP nameserver access would bypass the reviewed HTTPS SSRF boundary. TekDocs records the resolver as provenance and does not claim that a recursive response is a direct connection to an authoritative nameserver.

Raw RDAP and DNS responses are parsed, bounded, canonically digested, and discarded. Retained runs contain only source hostnames, digests, observed dates/registrar labels, record counts, and DNSSEC validation state. Normalized DNS answers and automated domain reviews are append-only. Entered registration data is never overwritten. Expiration, expiration-change, DNS-change, and collection-failure alerts are retained in the exact Workspace and projected in the Domains interface.

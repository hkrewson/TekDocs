# ADR 0074: Safe certificate monitoring

Date: 2026-08-12

Status: Accepted for `0.7.12`

Certificate endpoints are Entity-backed records under one exact registered-domain Workspace. An endpoint targets either the apex or an existing managed hostname and selects one fixed direct-TLS pair: HTTPS 443, SMTPS 465, IMAPS 993, or POP3S 995. Custom ports and STARTTLS are excluded so ordinary documentation cannot become a general socket-probing surface.

Collection occurs only in leased workers. The collector rejects IP literals, requires every DNS answer to be globally routable, pins one reviewed address for the socket, preserves the authored hostname for SNI, and requires TLS 1.2 or later. One bounded handshake captures the presented leaf/chain evidence; a separate CA-verifying handshake establishes public trust. Hostname matching is evaluated independently against SAN names, with CN fallback and conservative one-label wildcard semantics.

Raw DER/PEM certificates and exception values are discarded. Retained immutable runs contain only SHA-256 digests, bounded common names, validity times, SAN count/digest, hostname/trust results, and negotiated TLS metadata. Mutable endpoint fields are a current projection only. Expiration, certificate-change, validation-failure, and collection-failure alerts are append-only exact-Workspace records. PostgreSQL guards endpoint identity and terminal evidence and forces RLS on all three tables.

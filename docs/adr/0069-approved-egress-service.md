# ADR 0069: Approved egress service

Date: 2026-08-12

Status: Accepted for `0.7.7`

All application-controlled HTTP destinations must pass one approved public-HTTPS policy. The service normalizes DNS hostnames, rejects credentials/fragments/nonstandard ports/IP literals/internal names, requires every DNS answer to be globally routable, and returns one reviewed address for a pinned TLS connection that still verifies the original hostname and SNI. Callers retain narrower method, origin, content-type, body-size, and timeout policy. Redirects remain disabled. This reduces policy drift but does not make the remote service trusted.

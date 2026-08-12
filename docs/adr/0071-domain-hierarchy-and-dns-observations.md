# ADR 0071: Domain hierarchy and DNS observations

Date: 2026-08-12

Status: Accepted for `0.7.9`

Managed hostnames are stable exact-Workspace Entities below one registered-domain apex. Optional parent edges express hierarchy but must be true ancestors. Entered and discovered provenance remain explicit. DNS answers are append-only normalized observations with type, value, TTL, source, time, and digest; they never overwrite entered domain lifecycle data. Automated collection begins later.

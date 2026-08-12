# ADR 0072: Domain renewal review and scheduling

Date: 2026-08-12

Status: Accepted for `0.7.10`

An entered expiration date creates one exact-source reminder schedule and therefore appears in the authenticated calendar feed. Domain review is append-only evidence: current, stale, and conflict events retain entered and observed dates, source, note, actor, and time while updating a current-state projection. Observed values do not overwrite entered registration data. Requests never send notifications directly; the future reminder dispatcher will project due schedules through the existing transactional notification boundary.

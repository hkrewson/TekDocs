# ADR 0068: Shared reminder schedules

Date: 2026-08-12

Status: Accepted for `0.7.6`

Compliance, inventory, and domain monitoring use one reminder-schedule abstraction rather than separate deadline tables. Each schedule is an Entity owned by one explicit Workspace and points to one active source Entity in that same Workspace. Dedicated central permissions cover deadline projection and mutation; source access is never inferred from schedule ownership. Calendar feeds are authenticated, bounded, private downloads with stable event UIDs, not long-lived public bearer URLs. Notification production and observed domain renewal state remain later slices.

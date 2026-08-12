# ADR 0056: Portal and notification history stabilization

Date: 2026-08-11

Status: Accepted

## Decision

Portal documents and notification histories use signed seek cursors rather than offsets or fixed terminal windows. The cursor contains only the last ordering key plus its tenant/account/surface boundary, expires after 30 days, and is invalid when replayed by another account, surface, or delivery-state filter. Portal and inbox pages return at most 50 authorized records after scanning at most 100 candidates; delivery administration returns at most 100 metadata rows.

Inbox display authorization is evaluated in bounded organization groups. Source rows, publication-control actions, supersession state, client-safe reference entities, and organization permission decisions are loaded in sets, while the resulting projection remains equivalent to per-item authorization. This removes history-length N+1 behavior without turning a stored notification into an authorization grant.

The browser appends explicit older pages. The notification popover is an associated, labelled dialog: opening moves focus to its heading and Escape closes it and returns focus to the trigger. Loading, older-page failure, empty, and busy states remain visible without replacing already loaded history.

## Consequences

- Cursors are navigation capabilities, not durable bookmarks or API tokens. Clients must restart at the newest page after expiry or a scope/filter change.
- Page `count` describes the returned portal page; it is not a total that could become a client-data oracle.
- Inbox unread count remains bounded to the currently authorized scan rather than performing an unbounded permission-sensitive count.
- The 125-publication/250-notification fixture protects query and latency behavior at this subsystem scale; full 1.0 reference-dataset certification remains scheduled for public-beta hardening.
- `0.5.8` was not released. Its reminder/calendar deliverable is renumbered `0.5.10`; this slice adds no reminder topic or scheduling domain.
